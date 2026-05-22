from __future__ import annotations

import json
import logging
from typing import Any
from urllib import request, error

logger = logging.getLogger(__name__)


class Reranker:
    def __init__(self, api_key: str = "", model: str = "jina-reranker-v2-base-multilingual") -> None:
        self._api_key = api_key
        self._model = model

    def configure(self, api_key: str, model: str = "jina-reranker-v2-base-multilingual") -> None:
        self._api_key = api_key
        self._model = model

    def is_available(self) -> bool:
        return bool(self._api_key)

    def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_n: int = 5,
    ) -> list[dict[str, Any]]:
        if not self._api_key or not candidates:
            return candidates[:top_n]
        documents = []
        for c in candidates:
            payload = c.get("payload", {})
            doc_text = f"{payload.get('title', '')}: {payload.get('summary', payload.get('outline', ''))}"
            documents.append(doc_text[:1500])
        try:
            scores = self._call_jina_rerank(query, documents)
            if len(scores) != len(candidates):
                return candidates[:top_n]
            ranked = sorted(
                zip(candidates, scores),
                key=lambda x: -x[1],
            )
            return [c for c, _ in ranked[:top_n]]
        except Exception:
            logger.warning("Reranker failed, returning fallback candidates")
            return candidates[:top_n]

    def _call_jina_rerank(self, query: str, documents: list[str]) -> list[float]:
        endpoint = "https://api.jina.ai/v1/rerank"
        payload = {
            "model": self._model,
            "query": query,
            "documents": documents,
            "top_n": len(documents),
        }
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        req = request.Request(endpoint, data=data, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
                items = sorted(result.get("results", []), key=lambda x: x.get("index", 0))
                return [item.get("relevance_score", 0.0) for item in items]
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Reranker HTTP {exc.code}: {body}") from exc