"""Embeddings behind a port, so the provider is a config choice and never a code edit (ADR 0012).

An adapter turns texts into vectors and names itself with `model_id` and `dim`. Every stored vector
carries both, and a query only compares against vectors made by the same model, so two models never mix.
MI_EMBEDDINGS picks the adapter: "onnx" (default, a local multilingual model, no key) or "hash" (no
download, for offline runs). A hosted adapter (Voyage, Bedrock) is one more class with the same three members.
"""

import hashlib
import math
import os
import re
from functools import cache
from typing import Protocol

ONNX_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class Embedder(Protocol):
    model_id: str
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OnnxEmbedder:
    """A local multilingual model run by fastembed on ONNX Runtime. A German question finds an English block."""
    model_id, dim = ONNX_MODEL, 384

    def __init__(self):
        from fastembed import TextEmbedding
        self._model = TextEmbedding(self.model_id)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.embed(texts)]


class HashingEmbedder:
    """Words hashed into buckets. Deterministic and instant, but it only matches shared words, not meaning."""
    model_id, dim = "hashing-256", 256

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for word in re.findall(r"\w+", text.lower()):
            v[int(hashlib.sha256(word.encode()).hexdigest(), 16) % self.dim] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]


ADAPTERS = {"onnx": OnnxEmbedder, "hash": HashingEmbedder}


@cache
def embedder() -> Embedder:
    name = os.environ.get("MI_EMBEDDINGS", "onnx")
    if name not in ADAPTERS:
        raise ValueError(f"MI_EMBEDDINGS={name!r}; choose one of {sorted(ADAPTERS)}")
    return ADAPTERS[name]()


def literal(vector: list[float]) -> str:
    """The pgvector text form, so no extra client package is needed."""
    return "[" + ",".join(f"{x:.6f}" for x in vector) + "]"
