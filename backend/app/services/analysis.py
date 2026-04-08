import json
import logging
import re
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.core.sessions import Session, session_manager
from app.schemas.analysis import (
    AddDatasetRequest,
    AnalysisResponse,
    AskRequest,
    StartRequest,
    StartResponse,
    UploadResponse,
)
from app.services.ai import chat_full, chat_mini, extract_json
from app.services.datastore import (
    assess_data_quality,
    get_column_profile,
    get_sample,
    get_schema,
    get_stats,
    load_dataset,
    sanitize_table_name,
)
from app.services.session_store import save as save_session

logger = logging.getLogger(__name__)

# Max download size: 500 MB
MAX_DOWNLOAD_BYTES = 500 * 1024 * 1024

# Max AI code-generation retry attempts on sandbox/SQL errors
MAX_RETRIES = 3

# Allowed URL domains for dataset downloads (SSRF protection)
ALLOWED_DOWNLOAD_DOMAINS = {
    # data.gov + common resource hosts
    "catalog.data.gov",
    "data.gov",
    "data.cdc.gov",
    "data.census.gov",
    "ephtracking.cdc.gov",
    "aqs.epa.gov",
    "data.epa.gov",
    "data.transportation.gov",
    "data.cityofnewyork.us",
    "data.ca.gov",
    # World Bank
    "api.worldbank.org",
    "datacatalogapi.worldbank.org",
    "databank.worldbank.org",
    # HuggingFace
    "huggingface.co",
    "cdn-lfs.huggingface.co",
    "cdn-lfs-us-1.huggingface.co",
    # Other sources
    "metadata.sdohplace.org",
    "www2.census.gov",
    "raw.githubusercontent.com",
    "data.cms.gov",
    "dataverse.harvard.edu",
    # HUD GIS
    "hudgis-hud.opendata.arcgis.com",
    "opendata.arcgis.com",
    "services.arcgis.com",
    # FRED
    "api.stlouisfed.org",
    # BLS
    "api.bls.gov",
    "data.bls.gov",
    # CMAP
    "datahub.cmap.illinois.gov",
    "services.arcgisonline.com",
    # Census
    "api.census.gov",
    # OWID
    "ourworldindata.org",
    "catalog.ourworldindata.org",
    # OECD
    "sdmx.oecd.org",
    # EIA
    "api.eia.gov",
    # USASpending
    "api.usaspending.gov",
    # ClinicalTrials.gov
    "clinicaltrials.gov",
    # OpenFDA
    "api.fda.gov",
    # CFPB
    "www.consumerfinance.gov",
    # SEC EDGAR
    "efts.sec.gov",
    "www.sec.gov",
    "data.sec.gov",
    # Federal Register
    "www.federalregister.gov",
    # EPA
    "enviro.epa.gov",
    # FDIC
    "banks.data.fdic.gov",
}


def _validate_download_url(url: str) -> None:
    """Validate URL to prevent SSRF attacks.

    Defence-in-depth:
    1. Scheme must be https (or http).
    2. Hostname must be on the explicit allowlist — no wildcards.
    3. Direct IP addresses are blocked if private/loopback/link-local.
    4. DNS resolution is checked to guard against DNS-rebinding attacks
       where an allowed hostname resolves to a private IP at request time.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")

    hostname = parsed.hostname or ""

    # Block private/internal IPs (direct IP in URL)
    try:
        ip = ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            raise ValueError("Downloads from private IPs are not allowed")
    except ValueError as e:
        if "not allowed" in str(e):
            raise
        # Not an IP — it's a hostname, which is fine

    # Check against allowed domains (exact match or subdomain)
    if not any(hostname == d or hostname.endswith(f".{d}") for d in ALLOWED_DOWNLOAD_DOMAINS):
        raise ValueError(
            f"Downloads from '{hostname}' are not allowed. "
            "Only known data source domains are permitted."
        )

    # DNS-rebinding guard: resolve hostname and verify it doesn't point to
    # a private/loopback/link-local address.
    import socket

    try:
        for _family, _type, _proto, _canonname, sockaddr in socket.getaddrinfo(
            hostname, None, proto=socket.IPPROTO_TCP
        ):
            resolved = ip_address(sockaddr[0])
            if resolved.is_private or resolved.is_loopback or resolved.is_link_local:
                raise ValueError(f"Domain '{hostname}' resolves to private address {resolved}")
    except socket.gaierror:
        pass  # DNS failure will be caught by httpx at request time


def _sanitize_filename(fname: str) -> str:
    """Remove path separators and dangerous characters from filenames."""
    fname = fname.split("/")[-1].split("\\")[-1]
    fname = re.sub(r"[^\w.\-]", "_", fname)
    return fname[:255] if fname else "dataset.csv"


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences from AI-generated code."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.rsplit("```", 1)[0]
    return text.strip()


async def _download_file(url: str, dest_dir: Path, dataset_id: str) -> Path:
    # Validate the initial URL against the SSRF allowlist.
    _validate_download_url(url)  # CodeQL: url is validated here before use below

    async def _check_redirect(response: httpx.Response) -> None:
        """Validate each redirect target against the SSRF allowlist."""
        if response.is_redirect and "location" in response.headers:
            redirect_url = str(response.next_request.url) if response.next_request else ""
            if redirect_url:
                _validate_download_url(redirect_url)

    async with httpx.AsyncClient(
        timeout=120,
        follow_redirects=True,
        max_redirects=5,
        event_hooks={"response": [_check_redirect]},
    ) as client:
        async with client.stream("GET", url) as resp:  # noqa: S113
            resp.raise_for_status()

            # Check content-length if available
            content_length = resp.headers.get("content-length")
            if content_length and int(content_length) > MAX_DOWNLOAD_BYTES:
                raise ValueError("File exceeds maximum download size (500 MB)")

            # Determine filename
            content_disp = resp.headers.get("content-disposition", "")
            if "filename=" in content_disp:
                fname = content_disp.split("filename=")[-1].strip('" ')
            else:
                fname = url.split("/")[-1].split("?")[0]
                if not fname or "." not in fname:
                    fname = f"{sanitize_table_name(dataset_id)}.csv"

            # Infer extension from content-type if filename has no valid data extension
            known_exts = {
                ".csv",
                ".json",
                ".jsonl",
                ".parquet",
                ".xlsx",
                ".xls",
                ".pdf",
                ".xml",
                ".geojson",
                ".zip",
            }
            fname_ext = Path(fname).suffix.lower()
            if fname_ext not in known_exts:
                ct = resp.headers.get("content-type", "")
                if "json" in ct:
                    fname = f"{sanitize_table_name(dataset_id)}.json"
                elif "pdf" in ct:
                    fname = f"{sanitize_table_name(dataset_id)}.pdf"
                elif "xml" in ct:
                    fname = f"{sanitize_table_name(dataset_id)}.xml"
                elif "zip" in ct:
                    fname = f"{sanitize_table_name(dataset_id)}.zip"
                elif "csv" in ct or "text/plain" in ct:
                    fname = f"{sanitize_table_name(dataset_id)}.csv"
                else:
                    fname = f"{sanitize_table_name(dataset_id)}.csv"

            fname = _sanitize_filename(fname)
            dest = dest_dir / fname

            # Stream download with size check
            downloaded = 0
            with dest.open("wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    downloaded += len(chunk)
                    if downloaded > MAX_DOWNLOAD_BYTES:
                        dest.unlink(missing_ok=True)
                        raise ValueError("File exceeds maximum download size (500 MB)")
                    f.write(chunk)

        return dest


def _save_session_metadata(session: Session) -> None:
    """Persist session metadata for history/reload."""
    if not session.owner:
        return
    try:
        table_metadata = []
        for table in session.tables:
            try:
                cols = session.conn.execute(f"DESCRIBE {table}").fetchall()  # noqa: S608
                columns = [{"name": c[0], "type": c[1]} for c in cols]
                row_count = session.conn.execute(
                    f"SELECT COUNT(*) FROM {table}"  # noqa: S608
                ).fetchone()[0]
                table_metadata.append({"name": table, "columns": columns, "row_count": row_count})
            except Exception:  # noqa: S110
                pass

        save_session(
            session.owner,
            session.id,
            {
                "dataset_title": session.dataset_title,
                "dataset_description": session.dataset_description,
                "dataset_source": session.dataset_source,
                "dataset_id": session.dataset_id,
                "download_url": session.download_url,
                "original_question": session.question,
                "table_metadata": table_metadata,
                "chart_code": session.chart_code,
                "chat_history": session.chat_history[-50:],
            },
        )
    except Exception:
        logger.exception("Failed to save session metadata")


async def start_analysis(req: StartRequest, owner: str = "") -> StartResponse:
    session = session_manager.create(req.question, owner=owner)

    try:
        # Download dataset — always prefer source adapter (handles format quirks)
        from app.services.sources.bls import BLSSource
        from app.services.sources.cdc_places import CDCPlacesSource
        from app.services.sources.census import CensusSource
        from app.services.sources.cfpb import CFPBSource
        from app.services.sources.clinicaltrials import ClinicalTrialsSource
        from app.services.sources.cmap import CMAPSource
        from app.services.sources.cms import CMSSource
        from app.services.sources.datagov import DataGovSource
        from app.services.sources.eia import EIASource
        from app.services.sources.epa_ghgrp import EPAGHGRPSource
        from app.services.sources.fdic import FDICSource
        from app.services.sources.federal_register import FederalRegisterSource
        from app.services.sources.fred import FREDSource
        from app.services.sources.harvard_dataverse import HarvardDataverseSource
        from app.services.sources.hud import HUDSource
        from app.services.sources.huggingface import HuggingFaceSource
        from app.services.sources.kaggle_source import KaggleSource
        from app.services.sources.oecd import OECDSource
        from app.services.sources.openfda import OpenFDASource
        from app.services.sources.owid import OWIDSource
        from app.services.sources.sdohplace import SDOHPlaceSource
        from app.services.sources.sec_edgar import SECEdgarSource
        from app.services.sources.usaspending import USASpendingSource
        from app.services.sources.vdem import VDemSource
        from app.services.sources.worldbank import WorldBankSource

        source_adapters = {
            "data.gov": DataGovSource(),
            "worldbank": WorldBankSource(),
            "kaggle": KaggleSource(),
            "huggingface": HuggingFaceSource(),
            "sdohplace": SDOHPlaceSource(),
            "cms": CMSSource(),
            "harvard_dataverse": HarvardDataverseSource(),
            "hud": HUDSource(),
            "bls": BLSSource(),
            "fred": FREDSource(),
            "cmap": CMAPSource(),
            "census": CensusSource(),
            "owid": OWIDSource(),
            "oecd": OECDSource(),
            "vdem": VDemSource(),
            "eia": EIASource(),
            "usaspending": USASpendingSource(),
            "cdc_places": CDCPlacesSource(),
            "clinicaltrials": ClinicalTrialsSource(),
            "openfda": OpenFDASource(),
            "cfpb": CFPBSource(),
            "sec_edgar": SECEdgarSource(),
            "federal_register": FederalRegisterSource(),
            "epa_ghgrp": EPAGHGRPSource(),
            "fdic": FDICSource(),
        }
        adapter = source_adapters.get(req.source)

        file_path = None
        if adapter:
            try:
                file_path = await adapter.download(req.dataset_id, session.temp_dir)
            except Exception:
                logger.exception(
                    "Source adapter %s failed for dataset %s",
                    req.source,
                    req.dataset_id,
                )

        if not file_path and req.download_url:
            file_path = await _download_file(req.download_url, session.temp_dir, req.dataset_id)

        if not file_path:
            raise ValueError(f"Could not download dataset {req.dataset_id} from {req.source}")

        # Load into DuckDB
        logger.info("Loading %s (%s bytes) into DuckDB", file_path.name, file_path.stat().st_size)
        table_name = load_dataset(session.conn, file_path, req.dataset_id)
        session.tables.append(table_name)

        # Get metadata
        columns = get_schema(session.conn, table_name)
        row_count = session.conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        logger.info("Loaded %s: %d rows, %d columns", table_name, row_count, len(columns))
        stats = get_stats(session.conn, table_name)

        # Run data quality assessment
        data_quality = assess_data_quality(session.conn, table_name)

        # Generate preliminary charts
        charts, chart_code = await _generate_preliminary_charts(session, table_name, req.question)

        # Persist session metadata for history
        session.dataset_title = req.dataset_title or req.dataset_id
        session.dataset_description = req.dataset_description
        session.dataset_source = req.source
        session.dataset_id = req.dataset_id
        session.download_url = req.download_url or ""
        session.chart_code = chart_code or ""
        _save_session_metadata(session)

        return StartResponse(
            session_id=session.id,
            table_name=table_name,
            columns=columns,
            row_count=row_count,
            summary_stats={"stats": stats} if stats else {},
            data_quality=data_quality,
            charts=charts,
            chart_code=chart_code,
        )
    except Exception:
        logger.exception("Failed to start analysis")
        session_manager.remove(session.id)
        raise


async def upload_analysis(
    filename: str, contents: bytes, question: str, owner: str = ""
) -> UploadResponse:
    session = session_manager.create(question, owner=owner)

    try:
        # Write uploaded file to session temp dir
        safe_name = _sanitize_filename(filename)
        file_path = session.temp_dir / safe_name
        file_path.write_bytes(contents)

        # Derive table name from filename (without extension)
        base_name = safe_name.rsplit(".", 1)[0] if "." in safe_name else safe_name
        table_name = load_dataset(session.conn, file_path, base_name)
        session.tables.append(table_name)

        columns = get_schema(session.conn, table_name)
        row_count = session.conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        stats = get_stats(session.conn, table_name)

        data_quality = assess_data_quality(session.conn, table_name)

        charts, chart_code = await _generate_preliminary_charts(session, table_name, question)

        # Persist session metadata for history
        session.dataset_title = filename
        session.dataset_description = f"Uploaded file: {filename}"
        session.chart_code = chart_code or ""
        _save_session_metadata(session)

        return UploadResponse(
            session_id=session.id,
            table_name=table_name,
            columns=columns,
            row_count=row_count,
            summary_stats={"stats": stats} if stats else {},
            data_quality=data_quality,
            charts=charts,
            chart_code=chart_code,
        )
    except Exception:
        logger.exception("Failed to process uploaded file")
        session_manager.remove(session.id)
        raise


async def add_dataset(req: AddDatasetRequest) -> StartResponse:
    session = session_manager.get(req.session_id)
    if not session:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Session not found")

    if req.download_url:
        file_path = await _download_file(req.download_url, session.temp_dir, req.dataset_id)
    else:
        raise ValueError("download_url required for add-dataset")

    table_name = load_dataset(session.conn, file_path, req.dataset_id)
    session.tables.append(table_name)

    columns = get_schema(session.conn, table_name)
    row_count = session.conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    stats = get_stats(session.conn, table_name)

    return StartResponse(
        session_id=session.id,
        table_name=table_name,
        columns=columns,
        row_count=row_count,
        summary_stats={"stats": stats} if stats else {},
        charts=[],
    )


CHART_PROMPT = """\
You are a data analyst. Write Python code that creates 2-4 Plotly figures exploring
the dataset in relation to the user's question.

Rules:
- `df`, `pd`, `np`, `px`, `go`, `datetime`, `scipy_stats` are ALREADY available — \
do NOT import them.
- Do NOT re-assign or shadow builtins: str, int, float, list, dict, len, sum, min, max, type.
- NEVER use variable names starting with underscore (e.g. `_data`, `_temp`). \
The sandbox will reject them. Use plain names like `data`, `temp`, `cols`.
- When scaling/normalizing numeric columns, convert to float first \
(e.g. `vals = df[col].astype(float).values`) and work with NumPy arrays \
to avoid pandas dtype conflicts.
- For imputation, use `df.select_dtypes(include="number")` before calling `.median()` \
or `.mean()` — these fail on string/object columns.
- Always aggregate or sort data before plotting — never plot raw unsorted rows.
- Prefer `px` (plotly.express) for concise code.
- Assign figures to `fig1`, `fig2`, etc. (not a list).
- For column names with spaces use `df["Column Name"]` syntax.
- Set meaningful titles, axis labels, and legends on every figure.
- Do NOT call `fig.show()` or `print()`.
- Handle NaN values (dropna or fillna) and convert types if needed.
- For time series, sort by the date/time column before plotting.
- For categorical breakdowns, use groupby + aggregation.
- Do NOT use lifelines — compute any survival/KM curves manually with pandas.
- `scipy_stats` (scipy.stats) is available for t-tests, chi-square, correlation, etc.

Data-type specific guidance:
- Financial data: strip "$", ",", "%" from string columns before converting to float \
(e.g. `df["col"].str.replace(r"[$,%]", "", regex=True).astype(float)`).
- Geographic/state data: use `px.choropleth` with `locations=` and \
`locationmode="USA-states"` for US state-level maps, or `px.scatter_geo` for coordinates.
- Date/period columns: use `pd.to_datetime()` to parse dates. For BLS/FRED period codes \
(M01, Q1, etc.), build proper dates: `pd.to_datetime(df["year"] + df["period"].str[1:], \
format="%Y%m")`.
- Regulatory/FDA data: group by category/product/company and show top-N with \
`value_counts().head(N)`.
- Nested column names (with dots like "patient.age"): access with `df["patient.age"]`.

Respond with Python code only — no markdown fences, no explanation.\
"""


async def _generate_preliminary_charts(
    session: Session, table_name: str, question: str
) -> tuple[list[dict], str | None]:
    """Generate preliminary charts. Returns (figures, source_code)."""
    profile = get_column_profile(session.conn, table_name)
    sample = get_sample(session.conn, table_name, n=5)

    messages = [
        {
            "role": "developer",
            "content": CHART_PROMPT,
        },
        {
            "role": "user",
            "content": (
                f"Question: {question}\n\n"
                f"Table: {table_name}\n"
                f"Row count: {profile['row_count']}\n\n"
                f"Column profile:\n{json.dumps(profile['columns'], indent=2, default=str)}\n\n"
                f"Sample rows (first 5):\n{json.dumps(sample[:5], indent=2, default=str)}"
            ),
        },
    ]

    from app.services.sandbox import execute_code

    try:
        response_text = await chat_mini(
            messages,
            max_tokens=4096,
            reasoning_effort="medium",
        )
        code = _strip_code_fences(response_text)

        for attempt in range(MAX_RETRIES):
            sandbox_result = execute_code(code, session)
            if not sandbox_result.get("error"):
                return sandbox_result.get("figures", []), code

            logger.warning(
                "Preliminary chart code failed (attempt %d/%d): %s",
                attempt + 1,
                MAX_RETRIES,
                sandbox_result["error"],
            )
            if attempt + 1 >= MAX_RETRIES:
                break

            # Ask AI to fix the code
            messages.append({"role": "assistant", "content": code})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"That code produced an error: {sandbox_result['error']}\n"
                        "Fix the code and respond with corrected Python only."
                    ),
                }
            )
            response_text = await chat_mini(
                messages,
                max_tokens=4096,
                reasoning_effort="medium",
            )
            code = _strip_code_fences(response_text)

        return [], None
    except Exception:
        logger.exception("Failed to generate preliminary charts")
        return [], None


async def ask_question(req: AskRequest) -> AnalysisResponse:
    session = session_manager.get(req.session_id)
    if not session:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Session not found")

    # Build context about loaded tables
    table_info = []
    df_var_names = []
    for i, table in enumerate(session.tables):
        columns = get_schema(session.conn, table)
        sample = get_sample(session.conn, table, n=10)
        stats = get_stats(session.conn, table)
        var_name = "df" if i == 0 else f"df{i + 1}"
        df_var_names.append(f"`{var_name}` = {table}")
        table_info.append(
            {
                "table": table,
                "variable": var_name,
                "columns": columns,
                "sample": sample[:5],
                "stats": stats[:5] if isinstance(stats, list) else stats,
            }
        )

    df_mapping = ", ".join(df_var_names)

    # Build messages with chat history
    messages = [
        {
            "role": "developer",
            "content": (
                "You are a data analyst assistant. You have access "
                "to DuckDB tables loaded in a session.\n\n"
                "Choose a strategy:\n"
                '- "sql": Simple data lookups that return a table (no charts).\n'
                '- "python": Any analysis that needs charts or multi-step logic.\n\n'
                "Python sandbox rules:\n"
                f"- Pre-injected DataFrames: {df_mapping}\n"
                "- Pre-injected modules: pd, np, px (plotly.express), go (plotly.graph_objects), "
                "datetime, scipy_stats (scipy.stats)\n"
                "- Do NOT re-assign pd, np, px, go, str, int, float, list, dict, "
                "len, sum, min, max, type.\n"
                "- NEVER use variable names starting with underscore "
                "(e.g. _data, _temp). Use plain names like data, temp, cols.\n"
                "- When scaling/normalizing, convert to float first and use "
                "NumPy arrays to avoid pandas dtype conflicts.\n"
                "- For imputation, use df.select_dtypes(include='number') before "
                ".median() or .mean() — these fail on string columns.\n"
                "- Do NOT use lifelines — compute survival/KM curves "
                "manually with pandas. scipy_stats is available for t-tests, "
                "chi-square, correlation, etc.\n"
                "- Always sort/aggregate before plotting. Use px (plotly.express).\n"
                "- Assign figures to fig1, fig2, etc. Set titles and axis labels.\n"
                "- Do NOT call fig.show(). Handle NaN values.\n"
                "- Financial data: strip '$', ',', '%' from strings before float conversion.\n"
                "- Geographic data: use px.choropleth with locationmode='USA-states' "
                "for state-level maps.\n"
                "- Date/period columns: use pd.to_datetime() to parse. "
                "For BLS/FRED period codes (M01, Q1), build dates from year+period.\n"
                "- Nested column names (with dots): access as df['col.subcol'].\n\n"
                "Respond with JSON:\n"
                "{\n"
                '  "strategy": "sql" | "python",\n'
                '  "text_answer": "natural language explanation",\n'
                '  "sql": "DuckDB SQL query (if strategy=sql)",\n'
                '  "python_code": "Python code (if strategy=python)",\n'
                '  "follow_up_suggestions": ["question 1", "question 2"]\n'
                "}\n\n"
                f"Available tables: {json.dumps(table_info)}"
            ),
        },
    ]

    # Add chat history
    for msg in session.chat_history[-10:]:
        messages.append(msg)

    messages.append({"role": "user", "content": req.question})

    from app.services.sandbox import execute_code

    try:
        response_text = await chat_full(
            messages,
            max_tokens=8192,
            json_mode=True,
        )
        result = extract_json(response_text)

        charts = []
        data_table = None
        code_executed = None
        sql_executed = None
        last_error = None

        strategy = result.get("strategy", "sql")

        if strategy == "sql" and result.get("sql"):
            sql = result["sql"]
            sql_executed = sql
            for attempt in range(MAX_RETRIES):
                try:
                    df = session.conn.execute(sql).fetchdf()
                    data_table = {
                        "data": df.head(500).to_dict(orient="records"),
                        "columns": list(df.columns),
                    }
                    last_error = None
                    break
                except Exception as e:
                    last_error = str(e)
                    logger.warning(
                        "SQL execution failed (attempt %d/%d): %s",
                        attempt + 1,
                        MAX_RETRIES,
                        e,
                    )
                    if attempt + 1 >= MAX_RETRIES:
                        break
                    messages.append(
                        {
                            "role": "assistant",
                            "content": response_text,
                        }
                    )
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"The SQL query failed with: {e}\n"
                                "Fix the query and respond with the "
                                "same JSON format."
                            ),
                        }
                    )
                    response_text = await chat_full(
                        messages,
                        max_tokens=8192,
                        json_mode=True,
                    )
                    result = extract_json(response_text)
                    sql = result.get("sql", sql)
                    sql_executed = sql

            if last_error:
                result["text_answer"] = f"{result.get('text_answer', '')} (SQL error: {last_error})"

        elif strategy == "python" and result.get("python_code"):
            code = result["python_code"]
            code_executed = code
            for attempt in range(MAX_RETRIES):
                sandbox_result = execute_code(code, session)
                if not sandbox_result.get("error"):
                    charts.extend(sandbox_result.get("figures", []))
                    if sandbox_result.get("dataframes"):
                        df_info = sandbox_result["dataframes"][0]
                        data_table = {
                            "data": df_info["data"],
                            "columns": df_info["columns"],
                        }
                    last_error = None
                    break

                last_error = sandbox_result["error"]
                logger.warning(
                    "Python code failed (attempt %d/%d): %s",
                    attempt + 1,
                    MAX_RETRIES,
                    last_error,
                )
                if attempt + 1 >= MAX_RETRIES:
                    break

                messages.append(
                    {
                        "role": "assistant",
                        "content": response_text,
                    }
                )
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"The Python code failed with: {last_error}\n"
                            "Fix the code and respond with the "
                            "same JSON format."
                        ),
                    }
                )
                response_text = await chat_full(
                    messages,
                    max_tokens=8192,
                    json_mode=True,
                )
                result = extract_json(response_text)
                code = result.get("python_code", code)
                code_executed = code

            if last_error:
                result["text_answer"] = (
                    f"{result.get('text_answer', '')} (Code error: {last_error})"
                )

        # Update chat history
        session.chat_history.append({"role": "user", "content": req.question})
        session.chat_history.append(
            {
                "role": "assistant",
                "content": result.get("text_answer", ""),
                "code_executed": code_executed,
                "sql_executed": sql_executed,
            }
        )
        _save_session_metadata(session)

        return AnalysisResponse(
            text_answer=result.get("text_answer"),
            charts=charts if charts else None,
            data_table=data_table,
            code_executed=code_executed,
            sql_executed=sql_executed,
            follow_up_suggestions=result.get("follow_up_suggestions", []),
        )
    except Exception:
        logger.exception("Failed to process question")
        return AnalysisResponse(
            text_answer=(
                "Sorry, I encountered an error processing your question. Please try rephrasing."
            ),
            follow_up_suggestions=[
                "Can you summarize the data?",
                "What columns are available?",
            ],
        )


async def reload_session(saved: dict, owner: str) -> dict:
    """Re-download dataset and re-run chart code from a saved session."""
    session = session_manager.create(saved.get("original_question", ""), owner=owner)

    try:
        source = saved.get("dataset_source", "")
        dataset_id = saved.get("dataset_id", "")
        download_url = saved.get("download_url", "")

        # Re-download using the same logic as start_analysis
        from app.services.sources.bls import BLSSource
        from app.services.sources.cdc_places import CDCPlacesSource
        from app.services.sources.census import CensusSource
        from app.services.sources.cfpb import CFPBSource
        from app.services.sources.clinicaltrials import ClinicalTrialsSource
        from app.services.sources.cmap import CMAPSource
        from app.services.sources.cms import CMSSource
        from app.services.sources.datagov import DataGovSource
        from app.services.sources.eia import EIASource
        from app.services.sources.epa_ghgrp import EPAGHGRPSource
        from app.services.sources.fdic import FDICSource
        from app.services.sources.federal_register import FederalRegisterSource
        from app.services.sources.fred import FREDSource
        from app.services.sources.harvard_dataverse import HarvardDataverseSource
        from app.services.sources.hud import HUDSource
        from app.services.sources.huggingface import HuggingFaceSource
        from app.services.sources.kaggle_source import KaggleSource
        from app.services.sources.oecd import OECDSource
        from app.services.sources.openfda import OpenFDASource
        from app.services.sources.owid import OWIDSource
        from app.services.sources.sdohplace import SDOHPlaceSource
        from app.services.sources.sec_edgar import SECEdgarSource
        from app.services.sources.usaspending import USASpendingSource
        from app.services.sources.vdem import VDemSource
        from app.services.sources.worldbank import WorldBankSource

        source_adapters = {
            "data.gov": DataGovSource(),
            "worldbank": WorldBankSource(),
            "kaggle": KaggleSource(),
            "huggingface": HuggingFaceSource(),
            "sdohplace": SDOHPlaceSource(),
            "cms": CMSSource(),
            "harvard_dataverse": HarvardDataverseSource(),
            "hud": HUDSource(),
            "bls": BLSSource(),
            "fred": FREDSource(),
            "cmap": CMAPSource(),
            "census": CensusSource(),
            "owid": OWIDSource(),
            "oecd": OECDSource(),
            "vdem": VDemSource(),
            "eia": EIASource(),
            "usaspending": USASpendingSource(),
            "cdc_places": CDCPlacesSource(),
            "clinicaltrials": ClinicalTrialsSource(),
            "openfda": OpenFDASource(),
            "cfpb": CFPBSource(),
            "sec_edgar": SECEdgarSource(),
            "federal_register": FederalRegisterSource(),
            "epa_ghgrp": EPAGHGRPSource(),
            "fdic": FDICSource(),
        }
        adapter = source_adapters.get(source)

        file_path = None
        if adapter and dataset_id:
            try:
                file_path = await adapter.download(dataset_id, session.temp_dir)
            except Exception:
                logger.exception("Source adapter %s failed for reload", source)

        if not file_path and download_url:
            file_path = await _download_file(download_url, session.temp_dir, dataset_id)

        if not file_path:
            session_manager.remove(session.id)
            raise ValueError("Could not re-download dataset")

        # Load into DuckDB
        table_name = load_dataset(session.conn, file_path, dataset_id or "dataset")
        session.tables.append(table_name)

        columns = get_schema(session.conn, table_name)
        row_count = session.conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]

        data_quality = assess_data_quality(session.conn, table_name)

        # Re-run saved chart code if available
        charts = []
        chart_code = saved.get("chart_code", "")
        if chart_code:
            from app.services.sandbox import execute_code

            sandbox_result = execute_code(chart_code, session)
            if not sandbox_result.get("error"):
                charts = sandbox_result.get("figures", [])
            else:
                logger.warning("Saved chart code failed on reload: %s", sandbox_result["error"])

        # Restore session metadata
        session.dataset_title = saved.get("dataset_title", "")
        session.dataset_description = saved.get("dataset_description", "")
        session.dataset_source = source
        session.dataset_id = dataset_id
        session.download_url = download_url
        session.chart_code = chart_code

        return {
            "session_id": session.id,
            "table_name": table_name,
            "columns": columns,
            "row_count": row_count,
            "data_quality": data_quality,
            "charts": charts,
            "chart_code": chart_code,
            "chat_history": saved.get("chat_history", []),
            "dataset_title": saved.get("dataset_title", ""),
            "dataset_description": saved.get("dataset_description", ""),
            "dataset_source": source,
            "download_url": download_url,
        }
    except Exception:
        logger.exception("Failed to reload session")
        session_manager.remove(session.id)
        msg = "Failed to reload session. The dataset may no longer be available."
        raise ValueError(msg) from None
