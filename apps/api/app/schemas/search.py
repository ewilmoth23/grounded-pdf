from pydantic import BaseModel


class SearchMatchResponse(BaseModel):
    document_id: str
    document_name: str
    page_number: int
    excerpt: str
    score: float


class SearchResponse(BaseModel):
    query: str
    documents_available: bool
    matches: list[SearchMatchResponse]
