from qdrant_client import AsyncQdrantClient

from app.core.config import settings


def create_qdrant_client() -> AsyncQdrantClient:
    return AsyncQdrantClient(
        url=settings.qdrant_url,
        timeout=30,
    )
