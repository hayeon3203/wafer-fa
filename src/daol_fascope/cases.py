import requests
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

QDRANT_URL = "http://localhost:6333"
OLLAMA_EMBED_URL = "http://localhost:11434/api/embeddings"
COLLECTION = "wafer_defect_cases"
EMBED_MODEL = "nomic-embed-text"
EMBED_DIM = 768

_client = None


def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=QDRANT_URL)
        if not _client.collection_exists(COLLECTION):
            _client.create_collection(
                COLLECTION,
                vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
            )
    return _client


def embed(text: str) -> list[float]:
    response = requests.post(
        OLLAMA_EMBED_URL, json={"model": EMBED_MODEL, "prompt": text}, timeout=60
    )
    response.raise_for_status()
    return response.json()["embedding"]


def search_cases(query: str, top_k: int = 3) -> list[dict]:
    client = _get_client()
    hits = client.query_points(
        collection_name=COLLECTION, query=embed(query), limit=top_k
    ).points
    return [hit.payload for hit in hits]


def add_case(case_id: int, text: str, payload: dict) -> None:
    client = _get_client()
    client.upsert(
        collection_name=COLLECTION,
        points=[PointStruct(id=case_id, vector=embed(text), payload=payload)],
    )
