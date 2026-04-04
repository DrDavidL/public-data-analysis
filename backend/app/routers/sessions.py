from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_user
from app.services import session_store
from app.services.analysis import reload_session

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("/history")
async def list_history(email: str = Depends(get_current_user)) -> list[dict]:
    return session_store.list_sessions(email)


@router.post("/{session_id}/reload")
async def reload(session_id: str, email: str = Depends(get_current_user)) -> dict:
    saved = session_store.get_session(email, session_id)
    if not saved:
        raise HTTPException(status_code=404, detail="Saved session not found")
    try:
        return await reload_session(saved, owner=email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to reload session") from None


@router.delete("/{session_id}")
async def delete(session_id: str, email: str = Depends(get_current_user)) -> dict:
    if not session_store.delete(email, session_id):
        raise HTTPException(status_code=404, detail="Saved session not found")
    return {"ok": True}
