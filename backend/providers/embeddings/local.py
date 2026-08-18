"""Local embedding provider backed by fastembed (ONNX, in-process).

No document content ever leaves the process: fastembed loads a small ONNX
model once - downloaded from Hugging Face on first use, then cached on disk
under ``EMBEDDING_CACHE_DIR`` - and every embedding call after that runs
purely locally, with no per-document network call. This is Phase 2.6's
default, free-by-default provider.

Model construction (``TextEmbedding(...)``) validates and loads ONNX weights,
which is blocking and CPU-bound; it is deferred until the first ``embed()``
call (module-import must never touch disk/network - same rule as
``backend/database/session.py``'s lazy engine) and run in a worker thread so
it never blocks the event loop.
"""
import asyncio
import logging
from typing import Any, List, Optional, Sequence

from backend.config.settings import get_settings
from backend.core.exceptions import ConfigurationMissingError, ProviderUnavailableError
from backend.providers.embeddings.base import BaseEmbeddingProvider

logger = logging.getLogger("backend.providers.embeddings.local")


class LocalEmbeddingProvider(BaseEmbeddingProvider):
    name = "local"

    def __init__(
        self,
        *,
        model_name: Optional[str] = None,
        dimension: Optional[int] = None,
        cache_dir: Optional[str] = None,
    ) -> None:
        settings = get_settings()
        self._model_name = model_name or settings.embedding_model_name
        self._dimension = dimension or settings.embedding_dimension
        self._cache_dir = cache_dir if cache_dir is not None else settings.embedding_cache_dir
        self._model: Optional[Any] = None

    @property
    def is_configured(self) -> bool:
        # No secret is required to run a local model - it is available
        # whenever the dependency is installed, which requirements.txt pins.
        return True

    @property
    def dimension(self) -> int:
        return self._dimension

    def _load_model(self) -> Any:
        if self._model is None:
            try:
                from fastembed import TextEmbedding
            except ImportError as exc:  # pragma: no cover - pinned in requirements.txt
                raise ConfigurationMissingError(
                    "The local embedding model is not installed on this server."
                ) from exc
            kwargs: dict[str, Any] = {"model_name": self._model_name}
            if self._cache_dir:
                kwargs["cache_dir"] = self._cache_dir
            try:
                self._model = TextEmbedding(**kwargs)
            except Exception as exc:
                logger.warning(
                    "embedding_model_load_failed",
                    extra={"fields": {"model": self._model_name, "error": type(exc).__name__}},
                )
                raise ProviderUnavailableError(
                    "The local embedding model could not be loaded."
                ) from exc
        return self._model

    async def embed(self, texts: Sequence[str]) -> List[List[float]]:
        if not texts:
            return []
        return await asyncio.to_thread(self._embed_sync, list(texts))

    def _embed_sync(self, texts: List[str]) -> List[List[float]]:
        model = self._load_model()
        try:
            vectors = [vector.tolist() for vector in model.embed(texts)]
        except Exception as exc:
            logger.warning(
                "embedding_inference_failed",
                extra={"fields": {"model": self._model_name, "error": type(exc).__name__}},
            )
            raise ProviderUnavailableError(
                "The local embedding model failed to embed the given text."
            ) from exc
        for vector in vectors:
            if len(vector) != self._dimension:
                raise ProviderUnavailableError(
                    "The local embedding model produced a vector of unexpected width."
                )
        return vectors
