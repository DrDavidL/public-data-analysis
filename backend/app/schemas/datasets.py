from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    sources: list[str] | None = None  # None = all sources


class DatasetResult(BaseModel):
    source: str
    id: str
    title: str
    description: str
    formats: list[str] = []
    size_bytes: int | None = None
    download_url: str | None = None
    metadata: dict = {}
    ai_description: str | None = None
