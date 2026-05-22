from __future__ import annotations

import json
import re
from typing import Any
from urllib import request, error


class APIEmbedder:
    def __init__(self, api_key: str, base_url: str, model: str = "text-embedding-3-small") -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        endpoint = f"{self._base_url}/embeddings"
        payload = {"model": self._model, "input": texts}
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        req = request.Request(endpoint, data=data, headers=headers, method="POST")
        with request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
            items = sorted(result.get("data", []), key=lambda x: x.get("index", 0))
            return [item.get("embedding", []) for item in items]

    def embed_single(self, text: str) -> list[float]:
        results = self.embed([text])
        return results[0] if results else []


class FallbackEmbedder:
    _COMMON_WORDS: set[str] = {
        "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
        "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
        "没有", "看", "好", "自己", "这", "他", "她", "它", "们", "那",
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "of", "in", "to", "for", "with", "on", "at", "by", "from",
        "and", "or", "but", "not", "this", "that", "it", "as",
    }

    def __init__(self, dim: int = 256) -> None:
        self._dim = dim
        self._vocab: dict[str, int] = {}

    def _tokenize(self, text: str) -> list[str]:
        tokens: list[str] = []
        for match in re.finditer(r"[\u4e00-\u9fff]+|[a-zA-Z]+|\d+", text.lower()):
            token = match.group(0)
            if token not in self._COMMON_WORDS:
                tokens.append(token)
        return tokens

    def _build_vocab(self, corpus: list[str]) -> None:
        freq: dict[str, int] = {}
        for text in corpus:
            for token in self._tokenize(text):
                freq[token] = freq.get(token, 0) + 1
        sorted_tokens = sorted(freq.items(), key=lambda x: -x[1])[:self._dim * 3]
        for i, (token, _) in enumerate(sorted_tokens):
            self._vocab[token] = i % self._dim

    def update_vocab(self, texts: list[str]) -> None:
        if not self._vocab:
            self._build_vocab(texts)
            return
        existing = set(self._vocab.keys())
        for text in texts:
            for token in self._tokenize(text):
                if token not in existing:
                    existing.add(token)
                    self._vocab[token] = hash(token) % self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not self._vocab:
            self._build_vocab(texts)
        vectors: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self._dim
            tokens = self._tokenize(text)
            if not tokens:
                vectors.append(vec)
                continue
            for token in tokens:
                idx = self._vocab.get(token)
                if idx is not None:
                    vec[idx] += 1.0
            norm = sum(v * v for v in vec) ** 0.5
            if norm > 0:
                vec = [v / norm for v in vec]
            vectors.append(vec)
        return vectors

    def embed_single(self, text: str) -> list[float]:
        results = self.embed([text])
        return results[0] if results else [0.0] * self._dim
