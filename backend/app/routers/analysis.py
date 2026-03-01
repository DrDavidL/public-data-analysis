import logging
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.core.security import get_current_user
from app.core.sessions import session_manager
from app.schemas.analysis import (
    AddDatasetRequest,
    AnalysisResponse,
    AskRequest,
    ExecuteRequest,
    StartRequest,
    StartResponse,
    TablesResponse,
    UploadResponse,
)
from app.services.analysis import add_dataset, ask_question, start_analysis, upload_analysis
from app.services.sandbox import execute_code

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

# SQL statements that are NOT allowed (DuckDB filesystem/extension access)
_BLOCKED_SQL = re.compile(
    r"\b(COPY|INSTALL|LOAD|ATTACH|EXPORT|IMPORT)\b",
    re.IGNORECASE,
)

# DuckDB functions that read/write the filesystem
_BLOCKED_SQL_FUNCS = re.compile(
    r"\b(read_csv_auto|read_csv|read_parquet|read_json_auto|read_json|"
    r"read_text|read_blob|write_csv|write_parquet|glob|getenv)\s*\(",
    re.IGNORECASE,
)


def _get_session(session_id: str, email: str):
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.owner != email:
        raise HTTPException(status_code=403, detail="Access denied")
    return session


def _validate_sql(sql: str) -> None:
    """Block dangerous SQL statements."""
    stripped = sql.strip().rstrip(";").strip()
    if _BLOCKED_SQL.search(stripped):
        raise HTTPException(
            status_code=400,
            detail="Only SELECT queries are allowed",
        )
    if _BLOCKED_SQL_FUNCS.search(stripped):
        raise HTTPException(
            status_code=400,
            detail="File-access functions are not allowed in user SQL",
        )


ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".json", ".jsonl", ".parquet"}
MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB


@router.post("/upload", response_model=UploadResponse)
async def upload(
    file: UploadFile = File(...),
    question: str = Form(default="Summarize and visualize this dataset"),
    email: str = Depends(get_current_user),
) -> UploadResponse:
    # Validate extension
    fname = file.filename or "upload.csv"
    suffix = "." + fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # Read with size limit
    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="File exceeds 100 MB limit")

    return await upload_analysis(fname, contents, question, owner=email)


@router.post("/start", response_model=StartResponse)
async def start(body: StartRequest, email: str = Depends(get_current_user)) -> StartResponse:
    return await start_analysis(body, owner=email)


@router.post("/ask", response_model=AnalysisResponse)
async def ask(body: AskRequest, email: str = Depends(get_current_user)) -> AnalysisResponse:
    _get_session(body.session_id, email)
    return await ask_question(body)


@router.post("/add-dataset", response_model=StartResponse)
async def add(body: AddDatasetRequest, email: str = Depends(get_current_user)) -> StartResponse:
    _get_session(body.session_id, email)
    return await add_dataset(body)


@router.get("/tables/{session_id}", response_model=TablesResponse)
async def tables(session_id: str, email: str = Depends(get_current_user)) -> TablesResponse:
    session = _get_session(session_id, email)
    return TablesResponse(tables=session.table_schemas())


@router.post("/execute/{session_id}")
async def execute(
    session_id: str,
    body: ExecuteRequest,
    email: str = Depends(get_current_user),
) -> dict:
    session = _get_session(session_id, email)

    if body.language == "sql":
        _validate_sql(body.code)
        try:
            result_df = session.conn.execute(body.code).fetchdf()
            return {
                "data_table": result_df.head(500).to_dict(orient="records"),
                "columns": list(result_df.columns),
                "row_count": len(result_df),
            }
        except Exception:
            logger.exception("SQL execution error")
            return {"error": "SQL query failed. Check syntax and try again."}
    else:
        result = execute_code(body.code, session)
        return result
