from __future__ import annotations

import json
import logging
import math
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class QdrantLocalClient:
    def __init__(self, storage_dir: Path | str) -> None:
        self._storage_dir = Path(storage_dir)
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._collections: dict[str, dict[str, Any]] = {}
        self._load_all()

    @staticmethod
    def _safe_collection_name(collection_name: str) -> str:
        return "".join(c if c.isalnum() or c in "-_" else "_" for c in collection_name)

    def _collection_path(self, collection_name: str) -> Path:
        return self._storage_dir / self._safe_collection_name(collection_name)

    def _load_all(self) -> None:
        for item in self._storage_dir.iterdir():
            if item.is_dir() and (item / "meta.json").exists():
                try:
                    meta = json.loads((item / "meta.json").read_text(encoding="utf-8"))
                    points_path = item / "points.json"
                    points = []
                    if points_path.exists():
                        points = json.loads(points_path.read_text(encoding="utf-8"))
                    norm_cache = {}
                    for p in points:
                        vec = p.get("vector", [])
                        if vec:
                            norm_cache[p["id"]] = math.sqrt(sum(x * x for x in vec))
                    self._collections[item.name] = {"meta": meta, "points": points, "norm_cache": norm_cache}
                except Exception:
                    logger.warning("Failed to load Qdrant collection from %s", item.name)
                    continue

    def _save_collection(self, name: str) -> None:
        coll = self._collections.get(name)
        if not coll:
            return
        path = self._collection_path(name)
        path.mkdir(parents=True, exist_ok=True)
        (path / "meta.json").write_text(json.dumps(coll["meta"], ensure_ascii=False), encoding="utf-8")
        (path / "points.json").write_text(json.dumps(coll["points"], ensure_ascii=False), encoding="utf-8")

    def create_collection(self, collection_name: str, vector_size: int, distance: str = "Cosine") -> bool:
        safe_name = self._safe_collection_name(collection_name)
        path = self._collection_path(collection_name)
        if path.exists() and (path / "meta.json").exists():
            return False
        self._collections[safe_name] = {
            "meta": {"vector_size": vector_size, "distance": distance},
            "points": [],
            "norm_cache": {},
        }
        self._save_collection(safe_name)
        return True

    def collection_exists(self, collection_name: str) -> bool:
        return self._safe_collection_name(collection_name) in self._collections

    def upsert(self, collection_name: str, points: list[dict[str, Any]]) -> None:
        safe_name = self._safe_collection_name(collection_name)
        coll = self._collections.get(safe_name)
        if not coll:
            raise ValueError(f"Collection '{collection_name}' not found")
        existing = {p["id"]: p for p in coll["points"]}
        for point in points:
            existing[point["id"]] = point
            vec = point.get("vector", [])
            if vec:
                coll["norm_cache"][point["id"]] = math.sqrt(sum(x * x for x in vec))
        coll["points"] = list(existing.values())
        coll["_dirty"] = True
        self._save_collection(safe_name)

    def delete(self, collection_name: str, point_ids: list[int | str]) -> None:
        safe_name = self._safe_collection_name(collection_name)
        coll = self._collections.get(safe_name)
        if not coll:
            return
        ids_set = set(point_ids)
        coll["points"] = [p for p in coll["points"] if p["id"] not in ids_set]
        for pid in ids_set:
            coll["norm_cache"].pop(pid, None)
        coll["_dirty"] = True
        self._save_collection(safe_name)

    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 10,
        score_threshold: float | None = None,
        filter_condition: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        safe_name = self._safe_collection_name(collection_name)
        coll = self._collections.get(safe_name)
        if not coll:
            logger.info("Qdrant search: collection '%s' not found", safe_name)
            return []
        results: list[tuple[float, dict[str, Any]]] = []
        query_norm = math.sqrt(sum(x * x for x in query_vector))
        for point in coll["points"]:
            if filter_condition:
                if not self._match_filter(point.get("payload", {}), filter_condition):
                    continue
            vec = point.get("vector", [])
            if len(vec) != len(query_vector):
                continue
            cached_norm = coll.get("norm_cache", {}).get(point["id"])
            if cached_norm is not None and cached_norm > 0 and query_norm > 0:
                dot = sum(x * y for x, y in zip(query_vector, vec))
                score = dot / (query_norm * cached_norm)
            else:
                score = self._cosine_similarity(query_vector, vec)
            if score_threshold is not None and score < score_threshold:
                continue
            results.append((score, point))
        results.sort(key=lambda x: -x[0])
        return [
            {"id": p["id"], "score": s, "payload": p.get("payload", {})}
            for s, p in results[:limit]
        ]

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        if not a or not b:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    @staticmethod
    def _match_filter(payload: dict[str, Any], condition: dict[str, Any]) -> bool:
        for key, value in condition.items():
            if key not in payload:
                return False
            if isinstance(value, dict):
                if not QdrantLocalClient._match_filter(payload[key], value):
                    return False
            elif payload[key] != value:
                return False
        return True

    def count(self, collection_name: str) -> int:
        coll = self._collections.get(self._safe_collection_name(collection_name))
        return len(coll["points"]) if coll else 0

    def get_collection_info(self, collection_name: str) -> dict[str, Any] | None:
        coll = self._collections.get(self._safe_collection_name(collection_name))
        return coll["meta"] if coll else None
