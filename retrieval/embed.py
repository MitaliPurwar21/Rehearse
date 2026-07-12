"""Text embeddings for semantic resume retrieval.

Uses a small ONNX model through fastembed, so it runs locally and free with no PyTorch. The
model is lazy-loaded, so importing this module stays cheap and tests can inject a fake
embedder instead of loading the real thing.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

EMBED_DIM = 384
_MODEL_NAME = "BAAI/bge-small-en-v1.5"


@lru_cache(maxsize=1)
def _model() -> Any:
    from fastembed import TextEmbedding

    return TextEmbedding(_MODEL_NAME)


def embed(texts: list[str]) -> list[list[float]]:
    return [[float(x) for x in vec] for vec in _model().embed(texts)]
