from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.schemas.datasets import DatasetResult, SearchRequest
from app.services.dataset_search import search_datasets

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


@router.post("/search", response_model=list[DatasetResult])
async def search(
    body: SearchRequest, _email: str = Depends(get_current_user)
) -> list[DatasetResult]:
    return await search_datasets(body.question)
