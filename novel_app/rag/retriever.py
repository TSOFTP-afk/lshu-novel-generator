from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from novel_app.rag.embedder import APIEmbedder, FallbackEmbedder
from novel_app.rag.qdrant_client import QdrantLocalClient
from novel_app.rag.reranker import Reranker


class ChapterRetriever:
    def __init__(
        self,
        storage_dir: str,
        embedder: APIEmbedder | FallbackEmbedder | None = None,
        vector_size: int = 256,
    ) -> None:
        self._client = QdrantLocalClient(storage_dir)
        self._embedder = embedder or FallbackEmbedder(dim=vector_size)
        self._vector_size = vector_size
        self._reranker = Reranker()
        self._bm25_indexes: dict[str, dict[str, Any]] = {}

    def index_chapter(
        self,
        book_id: int,
        chapter_id: int,
        title: str,
        summary: str,
        outline: str = "",
        content_snippet: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        collection = self._collection_name(book_id)
        if not self._client.collection_exists(collection):
            self._client.create_collection(collection, self._vector_size)

        text_to_embed = f"{title}\n{outline}\n{summary}"[:3000]
        if not text_to_embed.strip():
            return

        vector = self._embedder.embed_single(text_to_embed)
        if not vector:
            return

        point_id = chapter_id
        payload = {
            "chapter_id": chapter_id,
            "book_id": book_id,
            "title": title,
            "summary": summary[:500],
            "outline": outline[:500],
            "content_snippet": content_snippet[:800],
            **(metadata or {}),
        }
        self._client.upsert(collection, [{"id": point_id, "vector": vector, "payload": payload}])

        self._update_bm25(book_id, chapter_id, text_to_embed, payload)

    def index_book_design(self, book_id: int, title: str, markdown: str) -> None:
        collection = self._collection_name(book_id)
        if not self._client.collection_exists(collection):
            self._client.create_collection(collection, self._vector_size)

        markdown = str(markdown or "").strip()
        if not markdown:
            return
        text_to_embed = f"书籍级设定：{title}\n{markdown}"[:3000]
        vector = self._embedder.embed_single(text_to_embed)
        if not vector:
            return

        point_id = "book_design"
        payload = {
            "doc_type": "book_design",
            "book_id": book_id,
            "title": f"书籍级设定：{title}",
            "summary": markdown[:900],
            "outline": "",
            "content_snippet": markdown[:1200],
        }
        self._client.upsert(collection, [{"id": point_id, "vector": vector, "payload": payload}])
        self._update_bm25(book_id, point_id, text_to_embed, payload)

    def remove_chapter(self, book_id: int, chapter_id: int) -> None:
        collection = self._collection_name(book_id)
        self._client.delete(collection, [chapter_id])
        bm25 = self._bm25_indexes.get(collection)
        if bm25 and chapter_id in bm25.get("docs", {}):
            del bm25["docs"][chapter_id]

    def search(
        self,
        book_id: int,
        query: str,
        top_k: int = 8,
        use_hybrid: bool = True,
        use_rerank: bool = False,
    ) -> list[dict[str, Any]]:
        collection = self._collection_name(book_id)
        if not self._client.collection_exists(collection):
            return []

        vector_results: list[dict[str, Any]] = []
        try:
            query_vector = self._embedder.embed_single(query)
            if query_vector:
                vector_results = self._client.search(collection, query_vector, limit=top_k * 2)
        except Exception:
            pass

        if not use_hybrid:
            return vector_results[:top_k]

        bm25_results = self._bm25_search(book_id, query, top_k * 2)
        merged = self._merge_results(vector_results, bm25_results, top_k * 2)

        if use_rerank and len(merged) > top_k:
            merged = self._reranker.rerank(query, merged, top_k)

        return merged[:top_k]

    def search_recent_chapters(
        self,
        book_id: int,
        query: str,
        chapter_count: int = 5,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        collection = self._collection_name(book_id)
        if not self._client.collection_exists(collection):
            return []
        results = self.search(book_id, query, top_k=chapter_count * 2, use_hybrid=True)
        return sorted(results, key=lambda r: r.get("payload", {}).get("chapter_id", 0), reverse=True)[:top_k]

    def build_context_from_results(
        self,
        results: list[dict[str, Any]],
        max_chars: int = 3000,
    ) -> str:
        if not results:
            return ""
        blocks: list[str] = []
        total = 0
        for r in results:
            payload = r.get("payload", {})
            title = str(payload.get("title", "")).strip()
            doc_type = str(payload.get("doc_type", "")).strip()
            if doc_type == "book_design":
                summary = str(payload.get("summary", "") or payload.get("content_snippet", "")).strip()
                if not summary:
                    continue
                block = f"- 书籍级设定：{summary[:500]}"
                if total + len(block) > max_chars:
                    if not blocks:
                        return block[:max_chars].rstrip()
                    break
                blocks.append(block)
                total += len(block)
                continue
            summary = str(payload.get("summary", "")).strip()
            outline = str(payload.get("outline", "")).strip()
            if not title:
                continue
            block = f"- {title}"
            if outline:
                block += f"（大纲：{outline[:120]}）"
            if summary:
                block += f"：{summary[:200]}"
            if total + len(block) > max_chars:
                if not blocks:
                    return block[:max_chars].rstrip()
                break
            blocks.append(block)
            total += len(block)
        return "\n".join(blocks)

    def _collection_name(self, book_id: int) -> str:
        return f"book_{book_id}"

    def _save_bm25_index(self, book_id: int) -> None:
        collection = self._collection_name(book_id)
        bm25 = self._bm25_indexes.get(collection)
        if not bm25:
            return
        path = Path(self._client._storage_dir) / collection / "bm25.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        serializable = {
            "doc_count": bm25["doc_count"],
            "avgdl": bm25["avgdl"],
            "df": dict(bm25["df"]),
            "doc_tokens": {
                str(k): {"tokens": v["tokens"], "length": v["length"]}
                for k, v in bm25["docs"].items()
            },
        }
        path.write_text(json.dumps(serializable, ensure_ascii=False), encoding="utf-8")

    def _load_bm25_index(self, book_id: int) -> None:
        collection = self._collection_name(book_id)
        path = Path(self._client._storage_dir) / collection / "bm25.json"
        if not path.exists():
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        self._bm25_indexes[collection] = {
            "doc_count": data["doc_count"],
            "avgdl": data["avgdl"],
            "df": defaultdict(int, data["df"]),
            "docs": {},
        }

    def _update_bm25(
        self,
        book_id: int,
        chapter_id: int | str,
        text: str,
        payload: dict[str, Any],
    ) -> None:
        collection = self._collection_name(book_id)
        if collection not in self._bm25_indexes:
            self._bm25_indexes[collection] = {
                "docs": {},
                "doc_count": 0,
                "avgdl": 0.0,
                "df": defaultdict(int),
            }
        bm25 = self._bm25_indexes[collection]
        tokens = self._tokenize(text)
        bm25["docs"][chapter_id] = {
            "tokens": tokens,
            "length": len(tokens),
            "payload": payload,
        }
        seen: set[str] = set()
        for token in tokens:
            if token not in seen:
                bm25["df"][token] += 1
                seen.add(token)
        bm25["doc_count"] = len(bm25["docs"])
        lengths = [d["length"] for d in bm25["docs"].values()]
        bm25["avgdl"] = sum(lengths) / max(1, len(lengths))
        self._save_bm25_index(book_id)

    def persist_bm25(self, book_id: int) -> None:
        self._save_bm25_index(book_id)

    def _bm25_search(
        self,
        book_id: int,
        query: str,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        collection = self._collection_name(book_id)
        bm25 = self._bm25_indexes.get(collection)
        if not bm25 or not bm25["docs"]:
            return []
        k1 = 1.5
        b = 0.75
        query_tokens = self._tokenize(query)
        scores: dict[int | str, float] = {}
        for doc_id, doc in bm25["docs"].items():
            score = 0.0
            dl = doc["length"]
            for token in query_tokens:
                df = bm25["df"].get(token, 0)
                if df == 0:
                    continue
                tf = doc["tokens"].count(token)
                idf = math.log(1 + (bm25["doc_count"] - df + 0.5) / (df + 0.5))
                numerator = tf * (k1 + 1)
                denominator = tf + k1 * (1 - b + b * dl / max(1, bm25["avgdl"]))
                score += idf * numerator / max(0.001, denominator)
            if score > 0:
                scores[doc_id] = score
        sorted_docs = sorted(scores.items(), key=lambda x: -x[1])[:top_k]
        max_score = max([s for _, s in sorted_docs], default=1.0)
        return [
            {
                "id": doc_id,
                "score": score / max_score,
                "payload": bm25["docs"][doc_id]["payload"],
            }
            for doc_id, score in sorted_docs
        ]

    def _merge_results(
        self,
        vector_results: list[dict[str, Any]],
        bm25_results: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        return self._rrf_merge(vector_results, bm25_results, top_k, k=60)

    @staticmethod
    def _rrf_merge(
        vector_results: list[dict[str, Any]],
        bm25_results: list[dict[str, Any]],
        top_k: int,
        k: int = 60,
    ) -> list[dict[str, Any]]:
        scores: dict[int | str, tuple[float, dict[str, Any]]] = {}
        for rank, r in enumerate(vector_results[:top_k * 2]):
            rid = r.get("id")
            if isinstance(rid, (int, str)):
                rrf = 1.0 / (k + rank + 1)
                scores[rid] = (rrf, r.get("payload", r))
        for rank, r in enumerate(bm25_results[:top_k * 2]):
            rid = r.get("id")
            if isinstance(rid, (int, str)):
                rrf = 1.0 / (k + rank + 1)
                if rid in scores:
                    scores[rid] = (scores[rid][0] + rrf, scores[rid][1])
                else:
                    scores[rid] = (rrf, r.get("payload", r))
        ranked = sorted(scores.items(), key=lambda x: -x[1][0])
        return [
            {
                "id": rid,
                "score": round(sc * 200, 4),
                "payload": payload,
            }
            for rid, (sc, payload) in ranked[:top_k]
        ]

    def search_with_recency(
        self,
        book_id: int,
        query: str,
        top_k: int = 5,
        recency_bias: float = 0.3,
    ) -> list[dict[str, Any]]:
        collection = self._collection_name(book_id)
        if not self._client.collection_exists(collection):
            return []
        recency_bias = max(0.0, min(1.0, float(recency_bias)))
        raw_candidates = self._client.search(collection, self._embedder.embed_single(query), limit=50)
        if not raw_candidates:
            return []
        candidates = [dict(r) for r in raw_candidates]
        max_chapter = max(
            ((r.get("id", 0) or 0) for r in candidates if isinstance(r.get("id"), int)),
            default=0,
        )
        if max_chapter <= 0:
            return self.search(book_id, query, top_k=top_k, use_hybrid=True)[:top_k]
        for r in candidates:
            rid = r.get("id")
            if isinstance(rid, int) and max_chapter > 0:
                recency_ratio = rid / max_chapter
                r["score"] = r.get("score", 0) * (1 - recency_bias) + recency_ratio * recency_bias
        candidates.sort(key=lambda x: -x.get("score", 0))
        return candidates[:top_k]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        tokens: list[str] = []
        for match in re.finditer(r"[\u4e00-\u9fff]+|[a-zA-Z]+|\d+", text.lower()):
            token = match.group(0)
            if len(token) >= 2 or token.isdigit():
                tokens.append(token)
        return tokens
