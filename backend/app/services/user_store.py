"""Persistent user store — Azure Table Storage in production, in-memory fallback for local dev."""

import logging

logger = logging.getLogger(__name__)

_users: dict[str, str] = {}
_table_client = None


def init(connection_string: str) -> None:
    """Initialize the user store. Uses Azure Table Storage if connection string is provided."""
    global _table_client  # noqa: PLW0603

    if not connection_string:
        logger.info("No AZURE_STORAGE_CONNECTION_STRING — using in-memory user store")
        return

    from azure.data.tables import TableServiceClient

    service = TableServiceClient.from_connection_string(connection_string)
    _table_client = service.create_table_if_not_exists("users")
    logger.info("User store initialized with Azure Table Storage")


def register(email: str, hashed_password: str) -> bool:
    """Register a user. Returns False if user already exists."""
    email = email.lower()

    if _table_client is not None:
        from azure.core.exceptions import ResourceExistsError

        try:
            _table_client.create_entity(
                {
                    "PartitionKey": "users",
                    "RowKey": email,
                    "hashed_password": hashed_password,
                }
            )
            return True
        except ResourceExistsError:
            return False

    if email in _users:
        return False
    _users[email] = hashed_password
    return True


def get_password_hash(email: str) -> str | None:
    """Return the stored password hash for the email, or None if not found."""
    email = email.lower()

    if _table_client is not None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            entity = _table_client.get_entity("users", email)
            return entity["hashed_password"]
        except ResourceNotFoundError:
            return None

    return _users.get(email)


def exists(email: str) -> bool:
    """Check if a user exists."""
    return get_password_hash(email.lower()) is not None


def clear() -> None:
    """Clear in-memory store (tests only)."""
    _users.clear()
