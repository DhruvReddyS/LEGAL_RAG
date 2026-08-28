from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

from qdrant_client import AsyncQdrantClient, models

from app.core.config import settings
from app.core.qdrant import create_qdrant_client


GLOBAL_LEGAL_CORPUS = "global_legal_corpus"
POLICE_CASE_DATA = "police_case_data"
ADVOCATE_CASE_DATA = "advocate_case_data"


@dataclass(frozen=True)
class CollectionDefinition:
    name: str
    payload_indexes: dict[str, models.PayloadSchemaType]


COLLECTIONS = (
    CollectionDefinition(
        name=GLOBAL_LEGAL_CORPUS,
        payload_indexes={
            "text": models.PayloadSchemaType.TEXT,
            "source_type": models.PayloadSchemaType.KEYWORD,
            "act_name": models.PayloadSchemaType.KEYWORD,
            "section": models.PayloadSchemaType.KEYWORD,
            "jurisdiction": models.PayloadSchemaType.KEYWORD,
            "court": models.PayloadSchemaType.KEYWORD,
            "decision_date": models.PayloadSchemaType.DATETIME,
            "decision_year": models.PayloadSchemaType.INTEGER,
            "is_current": models.PayloadSchemaType.BOOL,
            "source_id": models.PayloadSchemaType.KEYWORD,
            "document_id": models.PayloadSchemaType.KEYWORD,
            "canonical_document_id": models.PayloadSchemaType.KEYWORD,
            "verified_official": models.PayloadSchemaType.BOOL,
            "quality_status": models.PayloadSchemaType.KEYWORD,
            "corpus_tier": models.PayloadSchemaType.KEYWORD,
        },
    ),
    CollectionDefinition(
        name=POLICE_CASE_DATA,
        payload_indexes={
            "text": models.PayloadSchemaType.TEXT,
            "case_id": models.PayloadSchemaType.UUID,
            "doc_type": models.PayloadSchemaType.KEYWORD,
            "uploaded_by": models.PayloadSchemaType.UUID,
            "document_id": models.PayloadSchemaType.UUID,
            "storage_object_id": models.PayloadSchemaType.UUID,
            "corpus_scope": models.PayloadSchemaType.KEYWORD,
        },
    ),
    CollectionDefinition(
        name=ADVOCATE_CASE_DATA,
        payload_indexes={
            "text": models.PayloadSchemaType.TEXT,
            "case_id": models.PayloadSchemaType.UUID,
            "doc_type": models.PayloadSchemaType.KEYWORD,
            "uploaded_by": models.PayloadSchemaType.UUID,
            "document_id": models.PayloadSchemaType.UUID,
            "storage_object_id": models.PayloadSchemaType.UUID,
            "corpus_scope": models.PayloadSchemaType.KEYWORD,
        },
    ),
)


def _validate_vector_schema(name: str, info: models.CollectionInfo) -> None:
    dense_vectors = info.config.params.vectors
    if not isinstance(dense_vectors, dict):
        raise RuntimeError(f"Collection {name!r} does not use named dense vectors")

    dense = dense_vectors.get(settings.qdrant_dense_vector_name)
    if dense is None:
        raise RuntimeError(
            f"Collection {name!r} is missing dense vector "
            f"{settings.qdrant_dense_vector_name!r}"
        )
    if dense.size != settings.embedding_dimension or dense.distance != models.Distance.COSINE:
        raise RuntimeError(
            f"Collection {name!r} has an incompatible dense-vector schema: "
            f"expected size={settings.embedding_dimension}, distance=Cosine"
        )

    sparse_vectors = info.config.params.sparse_vectors or {}
    if settings.qdrant_sparse_vector_name not in sparse_vectors:
        raise RuntimeError(
            f"Collection {name!r} is missing sparse vector "
            f"{settings.qdrant_sparse_vector_name!r}"
        )


async def ensure_collection(
    client: AsyncQdrantClient,
    definition: CollectionDefinition,
) -> dict[str, object]:
    created = False
    if not await client.collection_exists(definition.name):
        await client.create_collection(
            collection_name=definition.name,
            vectors_config={
                settings.qdrant_dense_vector_name: models.VectorParams(
                    size=settings.embedding_dimension,
                    distance=models.Distance.COSINE,
                )
            },
            sparse_vectors_config={
                settings.qdrant_sparse_vector_name: models.SparseVectorParams(
                    modifier=models.Modifier.IDF,
                )
            },
        )
        created = True

    info = await client.get_collection(definition.name)
    _validate_vector_schema(definition.name, info)

    existing_indexes = set(info.payload_schema)
    created_indexes: list[str] = []
    for field_name, field_schema in definition.payload_indexes.items():
        if field_name in existing_indexes:
            existing_type = info.payload_schema[field_name].data_type
            if existing_type == field_schema:
                continue
            await client.delete_payload_index(
                collection_name=definition.name,
                field_name=field_name,
                wait=True,
            )
        await client.create_payload_index(
            collection_name=definition.name,
            field_name=field_name,
            field_schema=field_schema,
            wait=True,
        )
        created_indexes.append(field_name)

    return {
        "name": definition.name,
        "created": created,
        "created_indexes": created_indexes,
        "expected_indexes": sorted(definition.payload_indexes),
    }


async def initialize_qdrant() -> list[dict[str, object]]:
    client = create_qdrant_client()
    try:
        return [
            await ensure_collection(client, definition)
            for definition in COLLECTIONS
        ]
    finally:
        await client.close()


def main() -> None:
    result = asyncio.run(initialize_qdrant())
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
