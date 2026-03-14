"""Persistent session history — Azure Table Storage in production, in-memory fallback for dev."""

import json
import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

_sessions: dict[str, dict[str, dict]] = {}  # {email: {session_id: data}}
_table_client = None


def init(connection_string: str) -> None:
    global _table_client  # noqa: PLW0603

    if not connection_string:
        logger.info("Session store: using in-memory fallback")
        return

    from azure.data.tables import TableServiceClient

    service = TableServiceClient.from_connection_string(connection_string)
    _table_client = service.create_table_if_not_exists("sessions")
    logger.info("Session store initialized with Azure Table Storage")


def save(email: str, session_id: str, data: dict) -> None:
    email = email.lower()
    now = datetime.now(UTC).isoformat()

    if _table_client is not None:
        from azure.core.exceptions import ResourceExistsError

        entity = {
            "PartitionKey": email,
            "RowKey": session_id,
            "dataset_title": data.get("dataset_title", ""),
            "dataset_description": data.get("dataset_description", ""),
            "dataset_source": data.get("dataset_source", ""),
            "dataset_id": data.get("dataset_id", ""),
            "download_url": data.get("download_url", ""),
            "original_question": data.get("original_question", ""),
            "table_metadata": _truncate(json.dumps(data.get("table_metadata", []))),
            "chart_code": _truncate(data.get("chart_code", "")),
            "chat_history": _truncate(json.dumps(data.get("chat_history", []))),
            "created_at": data.get("created_at", now),
            "updated_at": now,
        }
        try:
            _table_client.create_entity(entity)
        except ResourceExistsError:
            _table_client.update_entity(entity, mode="Replace")
        return

    user_sessions = _sessions.setdefault(email, {})
    user_sessions[session_id] = {**data, "updated_at": now}
    if "created_at" not in user_sessions[session_id]:
        user_sessions[session_id]["created_at"] = now


def list_sessions(email: str) -> list[dict]:
    email = email.lower()

    if _table_client is not None:
        entities = _table_client.query_entities(f"PartitionKey eq '{email}'")
        results = []
        for e in entities:
            results.append(
                {
                    "session_id": e["RowKey"],
                    "dataset_title": e.get("dataset_title", ""),
                    "dataset_description": e.get("dataset_description", ""),
                    "dataset_source": e.get("dataset_source", ""),
                    "dataset_id": e.get("dataset_id", ""),
                    "download_url": e.get("download_url", ""),
                    "original_question": e.get("original_question", ""),
                    "created_at": e.get("created_at", ""),
                    "updated_at": e.get("updated_at", ""),
                }
            )
        results.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return results

    user_sessions = _sessions.get(email, {})
    results = []
    for sid, data in user_sessions.items():
        results.append(
            {
                "session_id": sid,
                "dataset_title": data.get("dataset_title", ""),
                "dataset_description": data.get("dataset_description", ""),
                "dataset_source": data.get("dataset_source", ""),
                "dataset_id": data.get("dataset_id", ""),
                "download_url": data.get("download_url", ""),
                "original_question": data.get("original_question", ""),
                "created_at": data.get("created_at", ""),
                "updated_at": data.get("updated_at", ""),
            }
        )
    results.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return results


def get_session(email: str, session_id: str) -> dict | None:
    email = email.lower()

    if _table_client is not None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            e = _table_client.get_entity(email, session_id)
            return {
                "session_id": e["RowKey"],
                "dataset_title": e.get("dataset_title", ""),
                "dataset_description": e.get("dataset_description", ""),
                "dataset_source": e.get("dataset_source", ""),
                "dataset_id": e.get("dataset_id", ""),
                "download_url": e.get("download_url", ""),
                "original_question": e.get("original_question", ""),
                "table_metadata": json.loads(e.get("table_metadata", "[]")),
                "chart_code": e.get("chart_code", ""),
                "chat_history": json.loads(e.get("chat_history", "[]")),
                "created_at": e.get("created_at", ""),
                "updated_at": e.get("updated_at", ""),
            }
        except ResourceNotFoundError:
            return None

    user_sessions = _sessions.get(email, {})
    return user_sessions.get(session_id)


def delete(email: str, session_id: str) -> bool:
    email = email.lower()

    if _table_client is not None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            _table_client.delete_entity(email, session_id)
            return True
        except ResourceNotFoundError:
            return False

    user_sessions = _sessions.get(email, {})
    return user_sessions.pop(session_id, None) is not None


def _truncate(value: str, max_bytes: int = 60000) -> str:
    """Truncate string to fit Azure Table Storage property limit (64KB)."""
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    return encoded[:max_bytes].decode("utf-8", errors="ignore")
