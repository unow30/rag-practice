import os
import threading
from typing import List

_model = None
_model_lock = threading.Lock()
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
BATCH_SIZE = 32


def get_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                import transformers
                transformers.logging.set_verbosity_error()
                from FlagEmbedding import BGEM3FlagModel
                _model = BGEM3FlagModel(EMBEDDING_MODEL, use_fp16=True)
    return _model


def embed_texts(texts: List[str]) -> List[List[float]]:
    model = get_model()
    all_vectors = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        output = model.encode(batch, batch_size=BATCH_SIZE, max_length=512)
        all_vectors.extend(output["dense_vecs"].tolist())
    return all_vectors


def embed_query(query: str) -> List[float]:
    model = get_model()
    output = model.encode([query], max_length=512)
    return output["dense_vecs"][0].tolist()
