"""Runtime email allowlist store (in-memory, seeded from config on startup)."""

_runtime_allowlist: set[str] = set()


def init(emails: list[str]) -> None:
    """Seed the runtime allowlist from config. Called once at startup."""
    _runtime_allowlist.update(e.lower() for e in emails if e)


def is_allowed(email: str) -> bool:
    """Check if an email is allowed. Empty allowlist means open access."""
    if not _runtime_allowlist:
        return True
    return email.lower() in _runtime_allowlist


def add(email: str) -> None:
    _runtime_allowlist.add(email.lower())


def remove(email: str) -> None:
    _runtime_allowlist.discard(email.lower())


def list_all() -> list[str]:
    return sorted(_runtime_allowlist)


def clear() -> None:
    """Clear the allowlist (used in tests)."""
    _runtime_allowlist.clear()
