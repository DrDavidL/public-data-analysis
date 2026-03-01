import re
from pathlib import Path

import duckdb
import pandas as pd


def sanitize_table_name(name: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    clean = re.sub(r"_+", "_", clean).strip("_").lower()
    if not clean or clean[0].isdigit():
        clean = "t_" + clean
    return clean[:63]


def load_dataset(conn: duckdb.DuckDBPyConnection, file_path: Path, table_name: str) -> str:
    table_name = sanitize_table_name(table_name)
    suffix = file_path.suffix.lower()
    # Escape single quotes in file path to prevent SQL injection
    safe_path = str(file_path).replace("'", "''")

    if suffix == ".csv":
        conn.execute(
            f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM read_csv_auto('{safe_path}')"
        )
    elif suffix == ".parquet":
        conn.execute(
            f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM read_parquet('{safe_path}')"
        )
    elif suffix in (".json", ".jsonl"):
        conn.execute(
            f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM read_json_auto('{safe_path}')"
        )
    elif suffix in (".xlsx", ".xls"):
        df = pd.read_excel(file_path)
        conn.register("_temp_df", df)
        conn.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM _temp_df")
        conn.unregister("_temp_df")
    else:
        # Try CSV as fallback
        conn.execute(
            f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM read_csv_auto('{safe_path}')"
        )

    return table_name


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
