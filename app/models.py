from pydantic import BaseModel, Field
from typing import Optional, List
import datetime

class ExplainRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=200)
    # Добавлены новые значения в комментарий для ясности
    level: str # 'simple', 'teenager', '5-year-old', 'custom_analogy', 'tldr', 'pros_cons', 'metaphor'
    analogy: Optional[str] = Field(None, max_length=100)

class ExplainResponse(BaseModel):
    explanation: str
    slug: Optional[str] = None # Возвращаем slug для возможного редиректа или ссылки

# Модель для хранения данных в JSON файле (без изменений)
class StoredExplanation(BaseModel):
    topic_raw: str
    slug: str
    level: str
    analogy: Optional[str] = None
    explanation_text: str
    meta_title: str
    meta_description: str
    created_at: datetime.datetime

# --- Новая модель для результатов поиска ---
class SearchResultItem(BaseModel):
    topic: str
    slug: str
    # Можно добавить фрагмент текста для предпросмотра, если нужно
    snippet: Optional[str] = None

class SearchResponse(BaseModel):
    results: List[SearchResultItem]