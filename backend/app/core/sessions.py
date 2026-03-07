import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import duckdb

from app.schemas.analysis import TableInfo

SESSION_TTL_SECONDS = 3600  # 1 hour


@dataclass
class Session:
    id: str
    conn: duckdb.DuckDBPyConnection
    question: str
    owner: str = ""
    tables: list[str] = field(default_factory=list)
    chat_history: list[dict] = field(default_factory=list)
    charts: list[dict] = field(default_factory=list)
    temp_dir: Path = field(default_factory=lambda: Path(tempfile.mkdtemp()))
    last_active: float = field(default_factory=time.time)
    # Metadata for session persistence (populated by analysis service)
    dataset_title: str = ""
    dataset_description: str = ""
    dataset_source: str = ""
    dataset_id: str = ""
    download_url: str = ""
    chart_code: str = ""

    def touch(self) -> None:
        self.last_active = time.time()

    def table_schemas(self) -> list[TableInfo]:
        result = []
        for table in self.tables:
            try:
                cols = self.conn.execute(f"DESCRIBE {table}").fetchall()  # noqa: S608
                columns = [{"name": c[0], "type": c[1]} for c in cols]
                row_count = self.conn.execute(
                    f"SELECT COUNT(*) FROM {table}"  # noqa: S608
                ).fetchone()[0]
                result.append(TableInfo(name=table, columns=columns, row_count=row_count))
            except Exception:  # noqa: S112
                continue
        return result

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:  # noqa: S110
            pass
        try:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:  # noqa: S110
            pass


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def create(self, question: str, owner: str = "") -> Session:
        self._cleanup_expired()
        session_id = uuid.uuid4().hex
        conn = duckdb.connect(":memory:")
        session = Session(id=session_id, conn=conn, question=question, owner=owner)
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        self._cleanup_expired()
        session = self._sessions.get(session_id)
        if session:
            session.touch()
        return session

    def remove(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session:
            session.close()

    def _cleanup_expired(self) -> None:
        now = time.time()
        expired = [
            sid for sid, s in self._sessions.items() if now - s.last_active > SESSION_TTL_SECONDS
        ]
        for sid in expired:
            self.remove(sid)


session_manager = SessionManager()
