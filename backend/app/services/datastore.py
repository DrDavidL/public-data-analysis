import json as _json
import logging
import re
import zipfile
from pathlib import Path

import duckdb
import pandas as pd

logger = logging.getLogger(__name__)


def sanitize_table_name(name: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    clean = re.sub(r"_+", "_", clean).strip("_").lower()
    if not clean or clean[0].isdigit():
        clean = "t_" + clean
    return clean[:63]


def load_dataset(conn: duckdb.DuckDBPyConnection, file_path: Path, table_name: str) -> str:
    table_name = sanitize_table_name(table_name)
    suffix = file_path.suffix.lower()

    # Validate file has content and isn't an HTML error page
    size = file_path.stat().st_size
    if size == 0:
        raise ValueError(f"Downloaded file is empty: {file_path.name}")
    if suffix not in (".parquet", ".xlsx", ".xls", ".pdf"):
        head = file_path.read_bytes()[:512]
        if head.lstrip().lower().startswith((b"<!doctype", b"<html")):
            raise ValueError(
                f"Downloaded file appears to be an HTML error page, not data: {file_path.name}"
            )

    # Escape single quotes in file path to prevent SQL injection
    safe_path = str(file_path).replace("'", "''")

    if suffix in (".csv", ".tsv", ".tab"):
        try:
            conn.execute(
                f"CREATE OR REPLACE TABLE {table_name} AS "
                f"SELECT * FROM read_csv_auto('{safe_path}')"
            )
        except (duckdb.ConversionException, duckdb.InvalidInputException):
            # Auto-detection can fail on messy CSVs (wrong types, undetected
            # quoting, column-count mismatches).  Retry with permissive settings.
            conn.execute(
                f"CREATE OR REPLACE TABLE {table_name} AS "
                f"SELECT * FROM read_csv_auto('{safe_path}', "
                f"all_varchar=true, quote='\"', ignore_errors=true)"
            )
    elif suffix == ".parquet":
        conn.execute(
            f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM read_parquet('{safe_path}')"
        )
    elif suffix in (".json", ".jsonl"):
        try:
            conn.execute(
                f"CREATE OR REPLACE TABLE {table_name} AS "
                f"SELECT * FROM read_json_auto('{safe_path}')"
            )
        except (duckdb.ConversionException, duckdb.InvalidInputException, duckdb.IOException):
            # Auto-detection can fail on deeply nested JSON (e.g., FDA FAERS,
            # SEC filings).  Flatten with pandas and register as a table.
            import json as _json

            raw = _json.loads(file_path.read_text())
            if isinstance(raw, dict):
                # Unwrap common API response wrappers
                for key in ("results", "data", "hits", "records", "items", "studies"):
                    if key in raw and isinstance(raw[key], list):
                        raw = raw[key]
                        break
                else:
                    raw = [raw]
            if isinstance(raw, list) and raw:
                df = pd.json_normalize(raw, max_level=2)
                conn.register("_temp_json_df", df)
                conn.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM _temp_json_df")
                conn.unregister("_temp_json_df")
            else:
                raise ValueError(  # noqa: B904
                    f"Cannot parse JSON structure in {file_path.name}"
                )
    elif suffix in (".xlsx", ".xls"):
        df = pd.read_excel(file_path)
        conn.register("_temp_df", df)
        conn.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM _temp_df")
        conn.unregister("_temp_df")
    elif suffix == ".pdf":
        df = _extract_pdf_tables(file_path)
        conn.register("_temp_pdf_df", df)
        conn.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM _temp_pdf_df")
        conn.unregister("_temp_pdf_df")
    elif suffix == ".xml":
        df = _parse_xml(file_path)
        conn.register("_temp_xml_df", df)
        conn.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM _temp_xml_df")
        conn.unregister("_temp_xml_df")
    elif suffix == ".geojson":
        df = _parse_geojson(file_path)
        conn.register("_temp_geo_df", df)
        conn.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM _temp_geo_df")
        conn.unregister("_temp_geo_df")
    elif suffix == ".zip":
        extracted = _extract_zip(file_path)
        if extracted is None:
            raise ValueError(f"ZIP archive contains no supported data files: {file_path.name}")
        return load_dataset(conn, extracted, table_name)
    else:
        # Try CSV as fallback
        try:
            conn.execute(
                f"CREATE OR REPLACE TABLE {table_name} AS "
                f"SELECT * FROM read_csv_auto('{safe_path}')"
            )
        except (duckdb.ConversionException, duckdb.InvalidInputException):
            conn.execute(
                f"CREATE OR REPLACE TABLE {table_name} AS "
                f"SELECT * FROM read_csv_auto('{safe_path}', "
                f"all_varchar=true, quote='\"', ignore_errors=true)"
            )

    return table_name


def _extract_pdf_tables(file_path: Path) -> pd.DataFrame:
    """Extract tables from a PDF using pdfplumber.

    Concatenates all tables found across pages. If no tables are detected,
    falls back to extracting text lines as a single-column DataFrame.
    """
    import pdfplumber

    all_dfs: list[pd.DataFrame] = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table_data in tables:
                if not table_data or len(table_data) < 2:
                    continue
                # First row as header
                header = [str(c or f"col_{i}") for i, c in enumerate(table_data[0])]
                rows = table_data[1:]
                df = pd.DataFrame(rows, columns=header)
                all_dfs.append(df)

    if all_dfs:
        result = pd.concat(all_dfs, ignore_index=True)
    else:
        # Fallback: extract text lines
        lines = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    lines.extend(text.split("\n"))
        if not lines:
            raise ValueError(f"PDF contains no extractable text or tables: {file_path.name}")
        result = pd.DataFrame({"text": lines})

    return result


def _parse_xml(file_path: Path) -> pd.DataFrame:
    """Parse an XML file into a flat DataFrame.

    Handles common government XML formats: tries to find repeating record
    elements and flatten their children into columns.
    """
    from lxml import etree

    tree = etree.parse(file_path)  # noqa: S320
    root = tree.getroot()

    # Strip namespaces for simpler access
    for elem in root.iter():
        if "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]

    # Find the most common repeating child element (= the "records")
    child_counts: dict[str, int] = {}
    for child in root:
        child_counts[child.tag] = child_counts.get(child.tag, 0) + 1

    if not child_counts:
        raise ValueError(f"XML file has no child elements: {file_path.name}")

    record_tag = max(child_counts, key=child_counts.get)

    records = []
    for elem in root.iter(record_tag):
        row: dict[str, str] = {}
        for child in elem:
            # Flatten one level of nesting
            if len(child) == 0:
                row[child.tag] = child.text or ""
            else:
                for subchild in child:
                    key = f"{child.tag}.{subchild.tag}"
                    row[key] = subchild.text or ""
        if row:
            records.append(row)

    if not records:
        raise ValueError(f"No records extracted from XML: {file_path.name}")

    return pd.DataFrame(records)


def _parse_geojson(file_path: Path) -> pd.DataFrame:
    """Parse a GeoJSON file, flattening feature properties into a DataFrame.

    Extracts geometry type and coordinates alongside all properties.
    """
    data = _json.loads(file_path.read_text())
    features = data.get("features", [])
    if not features:
        raise ValueError(f"GeoJSON contains no features: {file_path.name}")

    records = []
    for feature in features:
        row = dict(feature.get("properties", {}))
        geometry = feature.get("geometry", {})
        row["geometry_type"] = geometry.get("type", "")
        coords = geometry.get("coordinates")
        if coords:
            # For Point geometry, extract lat/lon directly
            if geometry.get("type") == "Point" and len(coords) >= 2:
                row["longitude"] = coords[0]
                row["latitude"] = coords[1]
            else:
                row["coordinates"] = str(coords)[:500]
        records.append(row)

    return pd.DataFrame(records)


def _extract_zip(file_path: Path) -> Path | None:
    """Extract the best data file from a ZIP archive.

    Searches for CSV, JSON, Parquet, Excel, GeoJSON, or XML files.
    Returns the path to the largest supported file found.
    """
    extract_dir = file_path.parent / f"{file_path.stem}_extracted"
    extract_dir.mkdir(exist_ok=True)

    supported = (".csv", ".tsv", ".json", ".jsonl", ".parquet", ".xlsx", ".xls", ".geojson", ".xml")
    best: Path | None = None
    best_size = 0

    with zipfile.ZipFile(file_path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            ext = Path(info.filename).suffix.lower()
            if ext in supported:
                zf.extract(info, extract_dir)
                extracted_path = extract_dir / info.filename
                if extracted_path.stat().st_size > best_size:
                    best = extracted_path
                    best_size = extracted_path.stat().st_size

    if best:
        logger.info("Extracted %s (%d bytes) from ZIP", best.name, best_size)

    return best


def get_schema(conn: duckdb.DuckDBPyConnection, table: str) -> list[dict]:
    cols = conn.execute(f"DESCRIBE {table}").fetchall()  # noqa: S608
    return [{"name": c[0], "type": c[1]} for c in cols]


def get_stats(conn: duckdb.DuckDBPyConnection, table: str) -> dict:
    try:
        stats_df = conn.execute(f"SUMMARIZE {table}").fetchdf()  # noqa: S608
        return stats_df.to_dict(orient="records")
    except Exception:
        return {}


def get_sample(conn: duckdb.DuckDBPyConnection, table: str, n: int = 20) -> list[dict]:
    df = conn.execute(f"SELECT * FROM {table} LIMIT {n}").fetchdf()  # noqa: S608
    return df.to_dict(orient="records")


def run_query(conn: duckdb.DuckDBPyConnection, sql: str) -> pd.DataFrame:
    return conn.execute(sql).fetchdf()


def assess_data_quality(conn: duckdb.DuckDBPyConnection, table: str) -> dict:
    """Run data quality checks and return a structured report."""
    row_count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
    if row_count == 0:
        return {
            "row_count": 0,
            "column_count": 0,
            "duplicate_rows": 0,
            "overall_score": 0,
            "summary": "Dataset is empty.",
            "columns": [],
            "findings": [{"severity": "error", "message": "Dataset contains no rows."}],
        }

    cols = conn.execute(f"DESCRIBE {table}").fetchall()  # noqa: S608
    column_count = len(cols)

    # Duplicate row count
    try:
        dup_count = conn.execute(
            f"SELECT COUNT(*) FROM (SELECT *, COUNT(*) AS n FROM {table} "  # noqa: S608
            f"GROUP BY ALL HAVING n > 1)"
        ).fetchone()[0]
    except Exception:
        dup_count = 0

    findings: list[dict] = []
    column_reports: list[dict] = []
    total_cells = row_count * column_count
    total_missing = 0

    for col_name, col_type, *_ in cols:
        escaped = col_name.replace('"', '""')
        quoted = f'"{escaped}"'

        report: dict = {"name": col_name, "type": col_type, "issues": []}

        try:
            null_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {quoted} IS NULL"  # noqa: S608
            ).fetchone()[0]
            distinct_count = conn.execute(
                f"SELECT COUNT(DISTINCT {quoted}) FROM {table}"  # noqa: S608
            ).fetchone()[0]
        except Exception:
            column_reports.append(report)
            continue

        total_missing += null_count
        missing_pct = round(100 * null_count / row_count, 1) if row_count else 0
        report["missing_count"] = null_count
        report["missing_pct"] = missing_pct
        report["distinct_count"] = distinct_count

        # High-missing column
        if missing_pct > 50:
            report["issues"].append("high_missing")
            findings.append(
                {
                    "severity": "warning",
                    "message": (
                        f'Column "{col_name}" is {missing_pct}% missing'
                        f" ({null_count}/{row_count} rows)."
                    ),
                }
            )
        elif missing_pct > 0:
            report["issues"].append("some_missing")

        # Constant column (only 1 distinct non-null value)
        if distinct_count <= 1 and null_count < row_count:
            report["issues"].append("constant")
            findings.append(
                {
                    "severity": "info",
                    "message": f'Column "{col_name}" has only 1 unique value (constant).',
                }
            )

        # All-null column
        if null_count == row_count:
            report["issues"].append("all_null")
            findings.append(
                {
                    "severity": "warning",
                    "message": f'Column "{col_name}" is entirely null.',
                }
            )

        # Numeric outlier detection via IQR
        type_upper = col_type.upper()
        is_numeric = any(
            t in type_upper
            for t in ("INT", "FLOAT", "DOUBLE", "DECIMAL", "NUMERIC", "BIGINT", "SMALLINT", "REAL")
        )
        if is_numeric and null_count < row_count:
            try:
                q_row = conn.execute(
                    f"SELECT PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY {quoted}) AS q1, "  # noqa: S608
                    f"PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY {quoted}) AS q3, "
                    f"MIN({quoted}), MAX({quoted}) "
                    f"FROM {table} WHERE {quoted} IS NOT NULL"
                ).fetchone()
                if q_row and q_row[0] is not None and q_row[1] is not None:
                    q1, q3 = float(q_row[0]), float(q_row[1])
                    iqr = q3 - q1
                    col_min, col_max = float(q_row[2]), float(q_row[3])
                    report["min"] = col_min
                    report["max"] = col_max
                    report["q1"] = round(q1, 4)
                    report["q3"] = round(q3, 4)
                    if iqr > 0:
                        lower_fence = q1 - 1.5 * iqr
                        upper_fence = q3 + 1.5 * iqr
                        outlier_count = conn.execute(
                            f"SELECT COUNT(*) FROM {table} "  # noqa: S608
                            f"WHERE {quoted} IS NOT NULL "
                            f"AND ({quoted} < {lower_fence} OR {quoted} > {upper_fence})"
                        ).fetchone()[0]
                        if outlier_count > 0:
                            outlier_pct = round(100 * outlier_count / row_count, 1)
                            report["outlier_count"] = outlier_count
                            report["outlier_pct"] = outlier_pct
                            report["issues"].append("outliers")
                            if outlier_pct > 5:
                                findings.append(
                                    {
                                        "severity": "info",
                                        "message": (
                                            f'Column "{col_name}" has {outlier_count} outliers '
                                            f"({outlier_pct}% of rows, IQR method)."
                                        ),
                                    }
                                )
            except Exception:
                pass

        # High cardinality check (unique-like text columns)
        if not is_numeric and distinct_count == row_count and row_count > 10:
            report["issues"].append("high_cardinality")

        column_reports.append(report)

    # Duplicate rows finding
    if dup_count > 0:
        dup_pct = round(100 * dup_count / row_count, 1)
        findings.append(
            {
                "severity": "warning" if dup_pct > 5 else "info",
                "message": f"Found {dup_count} duplicate row groups ({dup_pct}% of data).",
            }
        )

    # Overall completeness score (0-100)
    completeness = round(100 * (1 - total_missing / total_cells), 1) if total_cells else 100
    # Score: weighted combination
    dup_penalty = min(10, round(10 * dup_count / row_count, 1)) if row_count else 0
    overall_score = round(max(0, completeness - dup_penalty), 1)

    # Summary text
    issue_cols = sum(1 for c in column_reports if c.get("issues"))
    if overall_score >= 90 and issue_cols == 0:
        summary = "Data quality is excellent. No significant issues detected."
    elif overall_score >= 75:
        summary = f"Data quality is good. {issue_cols} column(s) have minor issues."
    elif overall_score >= 50:
        summary = f"Data quality is fair. {issue_cols} column(s) need attention."
    else:
        summary = f"Data quality is poor. {issue_cols} column(s) have significant issues."

    return {
        "row_count": row_count,
        "column_count": column_count,
        "duplicate_rows": dup_count,
        "completeness_pct": completeness,
        "overall_score": overall_score,
        "summary": summary,
        "columns": column_reports,
        "findings": findings,
    }


def get_column_profile(conn: duckdb.DuckDBPyConnection, table: str) -> dict:
    """Compute a rich per-column profile for AI chart generation."""
    row_count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
    cols = conn.execute(f"DESCRIBE {table}").fetchall()  # noqa: S608

    columns = []
    for col_name, col_type, *_ in cols:
        # Escape double quotes inside column names (DuckDB identifier quoting)
        escaped = col_name.replace('"', '""')
        quoted = f'"{escaped}"'

        try:
            null_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {quoted} IS NULL"  # noqa: S608
            ).fetchone()[0]
            distinct_count = conn.execute(
                f"SELECT COUNT(DISTINCT {quoted}) FROM {table}"  # noqa: S608
            ).fetchone()[0]
        except Exception:
            # Column name is unparseable — skip it
            columns.append({"name": col_name, "type": col_type})
            continue

        info: dict = {
            "name": col_name,
            "type": col_type,
            "null_count": null_count,
            "distinct_count": distinct_count,
        }

        # Categorical: list all distinct values if cardinality <= 20
        if distinct_count <= 20:
            try:
                vals = conn.execute(
                    f"SELECT DISTINCT {quoted} FROM {table} "  # noqa: S608
                    f"WHERE {quoted} IS NOT NULL ORDER BY {quoted}"
                ).fetchall()
                info["values"] = [v[0] for v in vals]
            except Exception:
                pass

        # Numeric stats
        type_upper = col_type.upper()
        if any(
            t in type_upper
            for t in ("INT", "FLOAT", "DOUBLE", "DECIMAL", "NUMERIC", "BIGINT", "SMALLINT", "REAL")
        ):
            try:
                stats_row = conn.execute(
                    f"SELECT MIN({quoted}), MAX({quoted}), AVG({quoted}) "  # noqa: S608
                    f"FROM {table} WHERE {quoted} IS NOT NULL"
                ).fetchone()
                if stats_row:
                    info["min"] = stats_row[0]
                    info["max"] = stats_row[1]
                    info["mean"] = (
                        round(float(stats_row[2]), 4) if stats_row[2] is not None else None
                    )
            except Exception:
                pass

        columns.append(info)

    return {"row_count": row_count, "columns": columns}
