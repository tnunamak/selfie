from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Memory(BaseModel):
    content: str = Field(..., description="Formatted conversation or content of the memory")
    source: str = Field(..., description="Source of the memory, e.g., API")
    importance: Optional[float] = Field(None, description="Importance score of the memory, [0, 1]")
    timestamp: datetime = Field(..., description="The time that the event happened at, e.g. the time a message was sent")

    def weaviate_dict(self, *args, **kwargs):
        d = super().model_dump(*args, **kwargs)
        d['timestamp'] = self.timestamp.isoformat() if self.timestamp else None
        return d


class ScoredMemory(Memory):
    score: float = Field(..., description="Overall score of the memory, for a query, [0, 1]")
    importance: Optional[float] = Field(..., description="Importance score of the memory, [0, 1]")
    relevance: float = Field(..., description="Relevance score of the memory, for a query, [0, 1]")
    recency: float = Field(..., description="Recency score of the memory, for a query (time), [0, 1]")
