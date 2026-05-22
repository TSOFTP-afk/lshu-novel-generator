from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from novel_app.rag.embedder import FallbackEmbedder
from novel_app.rag.qdrant_client import QdrantLocalClient
from novel_app.rag.retriever import ChapterRetriever


class FixedEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _text in texts]

    def embed_single(self, text: str) -> list[float]:
        return [1.0, 0.0]


@pytest.fixture
def temp_storage() -> str:
    with tempfile.TemporaryDirectory() as tmp:
        yield tmp


class TestFallbackEmbedder:
    def test_embed_single_returns_vector(self) -> None:
        embedder = FallbackEmbedder(dim=128)
        result = embedder.embed_single("这是一个测试句子。")
        assert len(result) == 128
        assert isinstance(result[0], float)

    def test_embed_multiple_returns_list(self) -> None:
        embedder = FallbackEmbedder(dim=64)
        texts = ["第一段文字。", "第二段文字。", "第三段文字。"]
        results = embedder.embed(texts)
        assert len(results) == 3
        assert all(len(v) == 64 for v in results)

    def test_empty_text_returns_zero_vector(self) -> None:
        embedder = FallbackEmbedder()
        result = embedder.embed_single("")
        assert len(result) == 256
        assert all(v == 0.0 for v in result)


class TestQdrantLocalClient:
    def test_create_collection(self, temp_storage: str) -> None:
        client = QdrantLocalClient(temp_storage)
        ok = client.create_collection("test_col", 128)
        assert ok
        assert client.collection_exists("test_col")

    def test_create_duplicate_collection(self, temp_storage: str) -> None:
        client = QdrantLocalClient(temp_storage)
        client.create_collection("test_col", 128)
        ok = client.create_collection("test_col", 128)
        assert not ok

    def test_upsert_and_search(self, temp_storage: str) -> None:
        client = QdrantLocalClient(temp_storage)
        client.create_collection("test_col", 3)
        client.upsert("test_col", [
            {"id": 1, "vector": [1.0, 0.0, 0.0], "payload": {"title": "第一章"}},
            {"id": 2, "vector": [0.0, 1.0, 0.0], "payload": {"title": "第二章"}},
            {"id": 3, "vector": [0.0, 0.0, 1.0], "payload": {"title": "第三章"}},
        ])
        results = client.search("test_col", [1.0, 0.1, 0.0], limit=2)
        assert len(results) == 2
        assert results[0]["id"] == 1

    def test_search_with_filter(self, temp_storage: str) -> None:
        client = QdrantLocalClient(temp_storage)
        client.create_collection("test_col", 3)
        client.upsert("test_col", [
            {"id": 1, "vector": [1.0, 0.0, 0.0], "payload": {"title": "第一章", "book_id": 1}},
            {"id": 2, "vector": [0.0, 1.0, 0.0], "payload": {"title": "第二章", "book_id": 2}},
        ])
        results = client.search("test_col", [0.0, 1.0, 0.0], filter_condition={"book_id": 2})
        assert len(results) == 1
        assert results[0]["payload"]["title"] == "第二章"

    def test_delete_points(self, temp_storage: str) -> None:
        client = QdrantLocalClient(temp_storage)
        client.create_collection("test_col", 3)
        client.upsert("test_col", [
            {"id": 1, "vector": [1.0, 0.0, 0.0]},
            {"id": 2, "vector": [0.0, 1.0, 0.0]},
        ])
        client.delete("test_col", [1])
        results = client.search("test_col", [1.0, 0.0, 0.0])
        assert len(results) == 1
        assert results[0]["id"] == 2

    def test_count(self, temp_storage: str) -> None:
        client = QdrantLocalClient(temp_storage)
        client.create_collection("test_col", 3)
        assert client.count("test_col") == 0
        client.upsert("test_col", [
            {"id": 1, "vector": [1.0, 0.0, 0.0]},
            {"id": 2, "vector": [0.0, 1.0, 0.0]},
        ])
        assert client.count("test_col") == 2

    def test_persistence_across_sessions(self, temp_storage: str) -> None:
        client1 = QdrantLocalClient(temp_storage)
        client1.create_collection("persist_col", 3)
        client1.upsert("persist_col", [{"id": 1, "vector": [1.0, 0.0, 0.0], "payload": {"title": "测试"}}])

        client2 = QdrantLocalClient(temp_storage)
        assert client2.collection_exists("persist_col")
        results = client2.search("persist_col", [1.0, 0.0, 0.0])
        assert len(results) == 1
        assert results[0]["payload"]["title"] == "测试"

    def test_special_collection_name_persists_with_safe_key(self, temp_storage: str) -> None:
        client1 = QdrantLocalClient(temp_storage)
        client1.create_collection("book:1", 3)
        client1.upsert("book:1", [{"id": 1, "vector": [1.0, 0.0, 0.0], "payload": {"title": "测试"}}])

        client2 = QdrantLocalClient(temp_storage)
        assert client2.collection_exists("book:1")
        assert client2.collection_exists("book_1")
        assert client2.count("book:1") == 1
        results = client2.search("book:1", [1.0, 0.0, 0.0])
        assert len(results) == 1
        assert results[0]["payload"]["title"] == "测试"


class TestChapterRetriever:
    @pytest.fixture
    def retriever(self, temp_storage: str) -> ChapterRetriever:
        r = ChapterRetriever(temp_storage)
        r.index_chapter(1, 1, "第一章：觉醒", "主角在车祸中觉醒了能力。", "车祸现场，主角险死还生。")
        r.index_chapter(1, 2, "第二章：初战", "主角第一次使用能力战斗。", "主角遭遇反派，被迫使用能力。")
        r.index_chapter(1, 3, "第三章：真相", "主角发现了能力的来源。", "导师揭示能力真相。")
        return r

    def test_index_and_search(self, retriever: ChapterRetriever) -> None:
        results = retriever.search(1, "能力的来源", top_k=2)
        assert len(results) >= 1

    def test_search_returns_scores(self, retriever: ChapterRetriever) -> None:
        results = retriever.search(1, "战斗", top_k=3)
        assert len(results) >= 1
        assert all("score" in r for r in results)
        assert all(isinstance(r["score"], (int, float)) for r in results)

    def test_search_unknown_book(self, retriever: ChapterRetriever) -> None:
        results = retriever.search(999, "测试", top_k=3)
        assert results == []

    def test_build_context_from_results(self, retriever: ChapterRetriever) -> None:
        results = retriever.search(1, "觉醒", top_k=2)
        context = retriever.build_context_from_results(results)
        assert "觉醒" in context
        assert "第一章" in context

    def test_build_context_returns_truncated_first_oversized_result(self, retriever: ChapterRetriever) -> None:
        results = [
            {
                "id": 1,
                "payload": {
                    "title": "超长章节",
                    "outline": "大纲" * 100,
                    "summary": "摘要" * 100,
                },
            }
        ]
        context = retriever.build_context_from_results(results, max_chars=40)
        assert context
        assert len(context) <= 40
        assert "超长章节" in context

    def test_remove_chapter(self, retriever: ChapterRetriever) -> None:
        retriever.remove_chapter(1, 1)
        results = retriever.search(1, "觉醒", top_k=3)
        assert not any(r["id"] == 1 for r in results)

    def test_book_design_indexes_as_special_rag_document(self, retriever: ChapterRetriever) -> None:
        retriever.index_book_design(1, "测试书", "# 书籍大纲模板\n\n## 1.2 篇幅与结构\n\n- [x] 长篇")
        results = retriever.search(1, "长篇", top_k=5)
        assert any(r["id"] == "book_design" for r in results)
        context = retriever.build_context_from_results(results)
        assert "书籍级设定" in context
        retriever.remove_chapter(1, 1)
        results_after_remove = retriever.search(1, "长篇", top_k=5)
        assert any(r["id"] == "book_design" for r in results_after_remove)

    def test_search_recent_chapters(self, retriever: ChapterRetriever) -> None:
        results = retriever.search_recent_chapters(1, "真相", top_k=2)
        if results:
            ids = [r.get("id") for r in results]
            assert ids == sorted(ids, reverse=True)

    def test_search_with_recency_weights_recency_once(self, temp_storage: str) -> None:
        retriever = ChapterRetriever(temp_storage, embedder=FixedEmbedder(), vector_size=2)
        retriever._client.create_collection("book_1", 2)
        retriever._client.upsert(
            "book_1",
            [
                {"id": 1, "vector": [1.0, 0.0], "payload": {"title": "旧章节"}},
                {"id": 10, "vector": [1.0, 0.0], "payload": {"title": "新章节"}},
            ],
        )

        results = retriever.search_with_recency(1, "任意查询", top_k=2, recency_bias=0.3)

        assert [item["id"] for item in results] == [10, 1]
        assert results[0]["score"] == pytest.approx(1.0)
        assert results[1]["score"] == pytest.approx(0.73)
