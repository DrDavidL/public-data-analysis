from typing import Literal

from pydantic import BaseModel, Field


class StartRequest(BaseModel):
    source: str = Field(max_length=50)
    dataset_id: str = Field(max_length=500)
    question: str = Field(min_length=1, max_length=2000)
    download_url: str | None = Field(default=None, max_length=2000)


class UploadResponse(BaseModel):
    session_id: str
    table_name: str
    columns: list[dict]
    row_count: int
    summary_stats: dict = {}
    data_quality: dict = {}
    charts: list[dict] = []


class AddDatasetRequest(BaseModel):
    session_id: str = Field(max_length=64)
    source: str = Field(max_length=50)
    dataset_id: str = Field(max_length=500)
    download_url: str | None = Field(default=None, max_length=2000)


class StartResponse(BaseModel):
    session_id: str
    table_name: str
    columns: list[dict]
    row_count: int
    summary_stats: dict = {}
    data_quality: dict = {}
    charts: list[dict] = []


class AskRequest(BaseModel):
    session_id: str = Field(max_length=64)
    question: str = Field(min_length=1, max_length=5000)


class ExecuteRequest(BaseModel):
    code: str = Field(max_length=50000)
    language: Literal["python", "sql"] = "python"


class PlotlySpec(BaseModel):
    data: list[dict]
    layout: dict


class AnalysisResponse(BaseModel):
    text_answer: str | None = None
    charts: list[dict] | None = None
    data_table: dict | None = None
    code_executed: str | None = None
    sql_executed: str | None = None
    follow_up_suggestions: list[str] = []


class TableInfo(BaseModel):
    name: str
    columns: list[dict]
    row_count: int


class TablesResponse(BaseModel):
    tables: list[TableInfo]
