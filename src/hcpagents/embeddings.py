"""Embeddings sit behind a port. The provider is a config choice, never a code edit (ADR 0012).

An adapter turns texts into vectors. It names itself with model_id and dim. Each stored vector holds both.
A query only compares with vectors from the same model. So two models never mix.

MI_EMBEDDINGS picks the adapter. The onnx one is the default: a local model for many languages, with no key.
The hash one needs no download and is for offline runs.
A hosted adapter (Voyage, Bedrock) is one more class with the same three members.
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
    """A local model run by fastembed on ONNX Runtime. It works in many languages, so a German question finds an English block."""
    model_id, dim = ONNX_MODEL, 384

    def __init__(self):
        from fastembed import TextEmbedding
        self._model = TextEmbedding(self.model_id)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._model.embed(texts)]


class HashingEmbedder:
    """Words hashed into buckets. It is fast and the same each time, but it matches shared words, not meaning."""
    model_id, dim = "hashing-256", 256

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(text) for text in texts]

    def _one(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for word in re.findall(r"\w+", text.lower()):
            vector[int(hashlib.sha256(word.encode()).hexdigest(), 16) % self.dim] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


ADAPTERS = {"onnx": OnnxEmbedder, "hash": HashingEmbedder}


@cache
def embedder() -> Embedder:
    name = os.environ.get("MI_EMBEDDINGS", "onnx")
    if name not in ADAPTERS:
        raise ValueError(f"MI_EMBEDDINGS={name!r}; choose one of {sorted(ADAPTERS)}")
    return ADAPTERS[name]()


def literal(vector: list[float]) -> str:
    """The pgvector text form. It needs no extra client package."""
    return "[" + ",".join(f"{part:.6f}" for part in vector) + "]"
