"""Real local embeddings using multilingual E5."""

import numpy as np
from sentence_transformers import SentenceTransformer


class MyEmbedder:
    def __init__(
        self,
        model_name: str = "intfloat/multilingual-e5-small",
        revision: str | None = None,
    ) -> None:
        self.model_name = model_name
        self.revision = revision
        self.model = SentenceTransformer(
            model_name,
            revision=revision,
            device="cpu",
        )
        self.dimensions = self.model.get_sentence_embedding_dimension()
        self.max_tokens = self.model.max_seq_length

        if self.dimensions != 384:
            raise ValueError(
                f"Expected 384 dimensions, got {self.dimensions}."
            )

    def _encode(
        self,
        texts: list[str],
        prefix: str,
    ) -> list[list[float]]:
        if not texts:
            return []

        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("Embedding inputs must be non-empty strings.")

        inputs = [prefix + text for text in texts]

        encoded = self.model.tokenizer(
            inputs,
            add_special_tokens=True,
            truncation=False,
            padding=False,
        )
        lengths = [len(ids) for ids in encoded["input_ids"]]

        oversized = [
            index for index, length in enumerate(lengths)
            if length > self.max_tokens
        ]
        if oversized:
            raise ValueError(
                f"Inputs exceed {self.max_tokens} tokens: {oversized}"
            )

        vectors = self.model.encode(
            inputs,
            batch_size=16,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )

        if vectors.shape != (len(texts), self.dimensions):
            raise ValueError(f"Unexpected vector shape: {vectors.shape}")

        if not np.isfinite(vectors).all():
            raise ValueError("Embedding contains non-finite values.")

        norms = np.linalg.norm(vectors, axis=1)
        if not np.allclose(norms, 1.0, atol=1e-4):
            raise ValueError("Embedding vectors are not unit-normalized.")

        return vectors.tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._encode(texts, "passage: ")

    def embed_query(self, question: str) -> list[float]:
        return self._encode([question], "query: ")[0]