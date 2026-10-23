"""
Modelos retornados pelo db_client.

Espelham os modelos que o Prisma gerava (mesmos nomes de campo, camelCase em
Product/PriceHistory e snake_case em SearchResult), para que web_server.py e
worker_tasks.py continuem acessando `p.history`, `p.imageUrl`, `h.scrapedAt`
e `r.model_dump(mode="json")` sem mudança.
"""

from datetime import datetime

from pydantic import BaseModel


class PriceHistory(BaseModel):
    id: str
    price: float | None = None
    inStock: bool = True
    scrapedAt: datetime
    productId: str


class Product(BaseModel):
    id: str
    url: str
    name: str | None = None
    imageUrl: str | None = None
    store: str
    status: str = "active"
    createdAt: datetime
    updatedAt: datetime
    # None quando o histórico não foi carregado (como o `include` do Prisma)
    history: list[PriceHistory] | None = None


class ProductGroup(BaseModel):
    """Mesmo formato do ProductGroup do frontend (@mv/types)."""
    id: str
    name: str
    productIds: list[str]
    createdAt: datetime


class SearchResult(BaseModel):
    id: str
    search_id: str
    query: str
    store: str
    title: str
    price: float | None = None
    currency: str = "BRL"
    image_url: str | None = None
    product_url: str
    rating: float | None = None
    review_count: int | None = None
    found_at: datetime
