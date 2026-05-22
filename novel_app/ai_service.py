from __future__ import annotations

import json
import ipaddress
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass
from threading import Event
from typing import Any
from urllib import error, request
from urllib.parse import urlparse

from novel_app.prompt_utils import prompt_value
from novel_app.structured_templates import (
    PROTAGONIST_TEMPLATE,
    SUPPORTING_CHARACTER_TEMPLATE,
    WORLD_TEMPLATE,
    book_outline_template,
)

DEFAULT_BASE_URL = "https://api.openai.com/v1"


@dataclass
class SkillCard:
    name: str
    category: str
    summary: str
    instruction: str
    use_cases: str = ""
    risk_note: str = ""

    def to_record(self) -> dict[str, str]:
        return {
            "name": self.name,
            "category": self.category,
            "summary": self.summary,
            "instruction": self.instruction,
            "use_cases": self.use_cases,
            "risk_note": self.risk_note,
        }


@dataclass
class SimpleAIService:
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    last_remote_error: str | None = None
    prompt_overrides: dict[str, str] | None = None

    @classmethod
    def from_env(cls) -> "SimpleAIService":
        service = cls()
        try:
            service.configure(
                api_key=os.getenv("OPENAI_API_KEY"),
                base_url=os.getenv("OPENAI_BASE_URL", DEFAULT_BASE_URL),
                model=os.getenv("OPENAI_MODEL"),
            )
        except ValueError as exc:
            service.configure(api_key=None, base_url=DEFAULT_BASE_URL, model=None)
            service._remember_remote_error("环境变量配置", exc)
        return service

    def configure(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_key = (api_key or "").strip() or None
        self.base_url = self._normalize_base_url(base_url)
        self.model = (model or "").strip() or None
        self.last_remote_error = None

    def set_model_router(self, model_router: Any) -> None:
        self._model_router = model_router

    def set_prompt_overrides(self, prompt_overrides: dict[str, str] | None) -> None:
        self.prompt_overrides = {
            str(key): str(value)
            for key, value in (prompt_overrides or {}).items()
        }

    def get_prompt_overrides(self) -> dict[str, str]:
        return dict(self.prompt_overrides or {})

    def prompt_text(self, key: str, default: str = "") -> str:
        return prompt_value(self.prompt_overrides or {}, key, default)

    def is_remote_configured(self) -> bool:
        return bool(self.api_key and self.model)

    def get_mode_label(self) -> str:
        if self.is_remote_configured():
            return f"远程接口 / {self.model}"
        return "本地 Mock"

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        cancel_event: Event | None = None,
        require_remote: bool = True,
    ) -> Iterator[str]:
        if require_remote:
            self.require_remote("AI 对话")
        safe_messages = [
            {
                "role": str(item.get("role", "user")),
                "content": str(item.get("content", "")),
            }
            for item in messages
            if isinstance(item, dict) and str(item.get("content", "")).strip()
        ]
        if self.api_key and self.model:
            try:
                for chunk in self._stream_chat_completion(safe_messages, temperature=0.45, cancel_event=cancel_event):
                    text = self._stream_delta_text(chunk)
                    if text:
                        yield text
                return
            except Exception as exc:
                self._remember_remote_error("AI 对话", exc)
                if require_remote:
                    raise
        yield from self._chunk_text(self._chat_mock(safe_messages), chunk_size=60, cancel_event=cancel_event)

    def clone(self) -> "SimpleAIService":
        return SimpleAIService(
            api_key=self.api_key,
            base_url=self.base_url,
            model=self.model,
            prompt_overrides=self.get_prompt_overrides(),
        )

    def require_remote(self, purpose: str = "当前功能") -> None:
        if not self.is_remote_configured():
            raise RuntimeError(f"{purpose}没有配置可用 AI 接口。")

    @staticmethod
    def _normalize_base_url(base_url: str | None) -> str:
        value = (base_url or DEFAULT_BASE_URL).strip().rstrip("/")
        if any(char in value for char in "\r\n\t"):
            raise ValueError("Base URL 不能包含换行或制表符。")
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Base URL 必须是 http:// 或 https:// 开头的完整地址。")
        if parsed.scheme == "http" and not SimpleAIService._is_local_http_host(parsed.hostname or ""):
            raise ValueError("远程 Base URL 必须使用 HTTPS；HTTP 仅允许本机模型接口。")
        return value

    @staticmethod
    def _is_local_http_host(host: str) -> bool:
        normalized = host.strip().strip("[]").lower().rstrip(".")
        if normalized in {"localhost", "127.0.0.1", "::1"}:
            return True
        try:
            return ipaddress.ip_address(normalized).is_loopback
        except ValueError:
            return False

    def _chat_completion_endpoint(self) -> str:
        return f"{self._normalize_base_url(self.base_url)}/chat/completions"

    def _remember_remote_error(self, action: str, exc: Exception) -> None:
        message = str(exc)
        if self.api_key:
            message = message.replace(self.api_key, "***")
        self.last_remote_error = f"{action}失败，已回退本地 Mock：{message[:800]}"

    def clear_last_remote_error(self) -> None:
        self.last_remote_error = None

    def consume_last_remote_error(self) -> str | None:
        message = self.last_remote_error
        self.last_remote_error = None
        return message

    def generate_draft(
        self,
        book_title: str,
        chapter_title: str,
        outline: str,
        current_content: str = "",
        summary_text: str = "",
        selected_skills: list[dict[str, Any]] | None = None,
        sourcebook_context: str = "",
    ) -> str:
        truth_file = "\n".join(
            [
                f"书名：{book_title or '未命名作品'}",
                f"章节：{chapter_title or '未命名章节'}",
                f"章节大纲：{outline or '暂无大纲'}",
                f"已有正文：{current_content or '暂无正文'}",
                f"设定/摘要：{summary_text or '暂无'}",
                sourcebook_context or "",
            ]
        )
        payload = self.multi_agent_generate_from_outline(
            book_title=book_title,
            chapter_title=chapter_title,
            outline=outline,
            current_content=current_content,
            truth_file=truth_file,
            selected_skills=selected_skills,
            sourcebook_context=sourcebook_context,
        )
        return str(payload.get("revised_content") or "")

    def continue_writing(
        self,
        book_title: str,
        chapter_title: str,
        outline: str,
        current_content: str,
        summary_text: str = "",
        selected_skills: list[dict[str, Any]] | None = None,
        sourcebook_context: str = "",
    ) -> str:
        return self._generate_by_mode(
            mode="continue",
            book_title=book_title,
            chapter_title=chapter_title,
            outline=outline,
            current_content=current_content,
            summary_text=summary_text,
            selected_skills=selected_skills,
            sourcebook_context=sourcebook_context,
        )

    def polish_text(
        self,
        book_title: str,
        chapter_title: str,
        outline: str,
        current_content: str,
        summary_text: str = "",
        selected_skills: list[dict[str, Any]] | None = None,
        sourcebook_context: str = "",
    ) -> str:
        return self._generate_by_mode(
            mode="polish",
            book_title=book_title,
            chapter_title=chapter_title,
            outline=outline,
            current_content=current_content,
            summary_text=summary_text,
            selected_skills=selected_skills,
            sourcebook_context=sourcebook_context,
        )

    def stream_generate(
        self,
        mode: str,
        book_title: str,
        chapter_title: str,
        outline: str,
        current_content: str = "",
        summary_text: str = "",
        selected_skills: list[dict[str, Any]] | None = None,
        sourcebook_context: str = "",
        cancel_event: Event | None = None,
        require_remote: bool = False,
    ) -> Iterator[str]:
        selected_skills = selected_skills or []
        if mode == "draft":
            truth_file = "\n".join(
                [
                    f"书名：{book_title or '未命名作品'}",
                    f"章节：{chapter_title or '未命名章节'}",
                    f"章节大纲：{outline or '暂无大纲'}",
                    f"已有正文：{current_content or '暂无正文'}",
                    f"设定/摘要：{summary_text or '暂无'}",
                    sourcebook_context or "",
                ]
            )
            payload = self.multi_agent_generate_from_outline(
                book_title=book_title,
                chapter_title=chapter_title,
                outline=outline,
                current_content=current_content,
                truth_file=truth_file,
                selected_skills=selected_skills,
                sourcebook_context=sourcebook_context,
                require_remote=require_remote,
                cancel_event=cancel_event,
            )
            yield from self._chunk_text(str(payload.get("revised_content") or ""), cancel_event=cancel_event)
            return
        if require_remote:
            self.require_remote("写作生成")
        if self.api_key and self.model:
            try:
                yield from self._generate_remote_stream(
                    mode=mode,
                    book_title=book_title,
                    chapter_title=chapter_title,
                    outline=outline,
                    current_content=current_content,
                    summary_text=summary_text,
                    selected_skills=selected_skills,
                    sourcebook_context=sourcebook_context,
                    cancel_event=cancel_event,
                )
                return
            except Exception as exc:
                self._remember_remote_error("流式生成", exc)
                if require_remote:
                    raise

        yield from self._chunk_text(
            self._generate_mock(
                mode=mode,
                book_title=book_title,
                chapter_title=chapter_title,
                outline=outline,
                current_content=current_content,
                summary_text=summary_text,
                selected_skills=selected_skills,
                sourcebook_context=sourcebook_context,
            ),
            cancel_event=cancel_event,
        )

    def summarize_chapter(
        self,
        book_title: str,
        chapter_title: str,
        outline: str,
        content: str,
        require_remote: bool = False,
    ) -> str:
        cleaned_content = content.strip()
        if not cleaned_content:
            return "当前章节还没有正文，暂时无法生成摘要。"

        self.require_remote("大纲同步")
        try:
            return self._summarize_remote(
                book_title=book_title,
                chapter_title=chapter_title,
                outline=outline,
                content=cleaned_content,
            )
        except Exception as exc:
            self._remember_remote_error("摘要同步", exc)
            raise

    def distill_skills(
        self,
        source_title: str,
        source_text: str,
        require_remote: bool = False,
    ) -> list[dict[str, str]]:
        cleaned_text = source_text.strip()
        if not cleaned_text:
            return []

        self.require_remote("Skills 提炼")
        try:
            return self._distill_remote(source_title, cleaned_text)
        except Exception as exc:
            self._remember_remote_error("Skills 提炼", exc)
            raise

    def distill_project_skills(
        self,
        source_title: str,
        source_text: str,
        source_url: str = "",
        license_note: str = "待确认",
        reusable_level: str = "pattern_only",
        require_remote: bool = False,
    ) -> list[dict[str, str]]:
        cleaned_text = source_text.strip()
        if not cleaned_text:
            return []

        self.require_remote("项目 Skills 提炼")
        try:
            return self._distill_project_remote(
                source_title=source_title,
                source_text=cleaned_text,
                source_url=source_url,
                license_note=license_note,
                reusable_level=reusable_level,
            )
        except Exception as exc:
            self._remember_remote_error("项目 Skills 提炼", exc)
            raise

    def analyze_document(self, text: str, require_remote: bool = False) -> str:
        """分析文档类型,返回 body/outline/character/world"""
        cleaned = text.strip()[:3000]
        if not cleaned:
            return "body"

        self.require_remote("智能导入分类")
        try:
            return self._analyze_remote(cleaned)
        except Exception as exc:
            self._remember_remote_error("文档分类", exc)
            raise

    def detect_chapter_structure(self, text: str, require_remote: bool = False) -> list[dict[str, Any]]:
        cleaned = text.strip()
        if not cleaned:
            return []

        self.require_remote("章节结构识别")
        try:
            from novel_app.agents import ChapterStructureAgent

            agent = ChapterStructureAgent(self._post_chat_completion)
            return agent.detect(cleaned)
        except Exception as exc:
            self._remember_remote_error("章节结构识别", exc)
            raise

    def detect_ai_probability(self, text: str) -> tuple[int, str]:
        cleaned = text.strip()
        if not cleaned:
            return 0, "none"
        if len(cleaned) < 200:
            return 0, "none"
        self.require_remote("AI 概率检测")
        prompt = (
            "请判断下面中文小说章节正文由 AI 生成或高度 AI 改写的概率。\n"
            "只输出 JSON 对象，不要解释。\n"
            "JSON 格式：{\"probability\": 0-100 的整数, \"level\": \"certain|high|medium|low|none\"}。\n"
            "分级规则：certain=几乎可确定或明显 AI/机器生成痕迹；high=高风险；medium=中等风险；low=低风险；none=基本无明显 AI 痕迹。\n"
            "注意：这是作者自检工具，请谨慎，不要把自然流畅或写得规整本身当作唯一证据。\n\n"
            f"正文：\n{cleaned[:8000]}"
        )
        result = self._post_chat_completion(
            messages=[
                {"role": "system", "content": "你是中文文本 AI 生成概率审阅器，只返回指定 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )
        raw_text = self._chat_completion_content(result, "AI 概率检测")
        payload = self._extract_json_object_payload(raw_text)
        probability = self._coerce_probability(payload.get("probability", 0))
        level = str(payload.get("level", "none")).strip().lower()
        return self._normalize_ai_probability(probability, level)

    def detect_chinese_typos(
        self,
        text: str,
        *,
        require_remote: bool = False,
    ) -> list[dict[str, Any]]:
        content = str(text or "")
        prompt_content = content.strip()
        if not prompt_content:
            return []
        if require_remote:
            self.require_remote("AI 纠错检测")
        if not self.is_remote_configured():
            return []
        prompt = (
            "请只检查下面中文小说章节正文中可能存在的错别字，不要评价文风、剧情或语法。\n"
            "只输出 JSON 数组，不要解释。每项字段：wrong, suggestion, context, confidence。\n"
            "wrong 必须是原文中连续出现的字或词；suggestion 是建议替换；confidence 为 0-1。\n"
            "如果没有错别字，输出 []。\n\n"
            f"章节正文：\n{prompt_content[:8000]}"
        )
        result = self._post_chat_completion(
            messages=[
                {"role": "system", "content": "你是中文小说错别字校对器，只返回 JSON 数组。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.05,
        )
        raw_text = self._chat_completion_content(result, "AI 纠错检测")
        try:
            payload = self._extract_json_payload(raw_text)
        except Exception as exc:
            if require_remote:
                raise RuntimeError("AI 纠错返回格式无效：未收到 JSON 数组。") from exc
            return []
        findings: list[dict[str, Any]] = []
        occupied_starts: set[int] = set()
        for item in payload[:80]:
            if not isinstance(item, dict):
                continue
            wrong = str(item.get("wrong", "") or "").strip()
            suggestion = str(item.get("suggestion", "") or "").strip()
            if not wrong or not suggestion or wrong == suggestion:
                continue
            start = content.find(wrong)
            while start in occupied_starts and start >= 0:
                start = content.find(wrong, start + len(wrong))
            if start < 0:
                continue
            occupied_starts.add(start)
            try:
                confidence = float(item.get("confidence", 0.75) or 0.75)
            except (TypeError, ValueError):
                confidence = 0.75
            findings.append(
                {
                    "start": start,
                    "end": start + len(wrong),
                    "wrong": wrong,
                    "suggestion": suggestion,
                    "severity": "medium" if confidence >= 0.8 else "low",
                    "dimension": "错别字(AI)",
                    "rule": "ai_typo_detection",
                    "confidence": max(0.0, min(1.0, confidence)),
                }
            )
        findings.sort(key=lambda item: int(item["start"]))
        return findings

    @staticmethod
    def _coerce_probability(value: Any) -> int:
        if isinstance(value, (int, float)):
            return max(0, min(100, int(round(value))))
        match = re.search(r"\d{1,3}", str(value))
        if not match:
            return 0
        return max(0, min(100, int(match.group(0))))

    @staticmethod
    def _level_from_probability(probability: int) -> str:
        if probability >= 92:
            return "certain"
        if probability >= 68:
            return "high"
        if probability >= 42:
            return "medium"
        if probability >= 18:
            return "low"
        return "none"

    def _normalize_ai_probability(self, probability: int, level: str) -> tuple[int, str]:
        probability = max(0, min(100, int(probability)))
        level = str(level).strip().lower()
        derived = self._level_from_probability(probability)
        if level not in {"certain", "high", "medium", "low", "none"}:
            return probability, derived
        if level == "certain" and probability >= 92:
            return 100, "certain"
        if level != derived:
            return probability, derived
        return probability, level

    def analyze_book(
        self,
        *,
        book_title: str,
        book_outline: str,
        chapters: list[dict[str, Any]],
        characters: list[dict[str, Any]] | None = None,
        world_entries: list[dict[str, Any]] | None = None,
        require_remote: bool = False,
    ) -> dict[str, Any]:
        if require_remote:
            self.require_remote("全书分析")
        characters = characters or []
        world_entries = world_entries or []
        if self.api_key and self.model:
            try:
                return self._analyze_book_remote(
                    book_title=book_title,
                    book_outline=book_outline,
                    chapters=chapters,
                    characters=characters,
                    world_entries=world_entries,
                )
            except Exception as exc:
                self._remember_remote_error("全书分析", exc)
                if require_remote:
                    raise
        return self._analyze_book_mock(book_title, book_outline, chapters, characters, world_entries)

    def analyze_book_level1(
        self,
        *,
        book_title: str,
        book_outline: str,
        chunk_text: str,
        chunk_index: int,
        total_chunks: int,
        chunk_id: str = "",
        chapter_ids: list[int] | None = None,
        extra_body: dict[str, Any] | None = None,
        require_remote: bool = True,
    ) -> dict[str, Any]:
        if require_remote:
            self.require_remote("全书分析一级")
        if not self.is_remote_configured():
            self.require_remote("全书分析一级")
        try:
            return self._analyze_book_level1_remote(
                book_title=book_title,
                book_outline=book_outline,
                chunk_text=chunk_text,
                chunk_index=chunk_index,
                total_chunks=total_chunks,
                chunk_id=chunk_id,
                chapter_ids=chapter_ids or [],
                extra_body=extra_body,
            )
        except Exception as exc:
            self._remember_remote_error("全书分析一级", exc)
            raise

    def analyze_book_level2(
        self,
        *,
        book_title: str,
        level1_results: list[dict[str, Any]],
        group_index: int,
        total_groups: int,
        extra_body: dict[str, Any] | None = None,
        require_remote: bool = True,
    ) -> dict[str, Any]:
        if require_remote:
            self.require_remote("全书分析二级")
        if not self.is_remote_configured():
            self.require_remote("全书分析二级")
        try:
            return self._analyze_book_level2_remote(
                book_title=book_title,
                level1_results=level1_results,
                group_index=group_index,
                total_groups=total_groups,
                extra_body=extra_body,
            )
        except Exception as exc:
            self._remember_remote_error("全书分析二级", exc)
            raise

    def analyze_book_level3(
        self,
        *,
        book_title: str,
        book_outline: str,
        level2_results: list[dict[str, Any]],
        chapters: list[dict[str, Any]],
        characters: list[dict[str, Any]] | None = None,
        world_entries: list[dict[str, Any]] | None = None,
        extra_body: dict[str, Any] | None = None,
        require_remote: bool = True,
    ) -> dict[str, Any]:
        if require_remote:
            self.require_remote("全书分析三级")
        if not self.is_remote_configured():
            self.require_remote("全书分析三级")
        try:
            return self._analyze_book_level3_draft_remote(
                book_title=book_title,
                book_outline=book_outline,
                level2_results=level2_results,
                chapters=chapters,
                characters=characters or [],
                world_entries=world_entries or [],
                extra_body=extra_body,
            )
        except Exception as exc:
            self._remember_remote_error("全书分析三级", exc)
            raise

    def analyze_book_level3_draft(
        self,
        *,
        book_title: str,
        book_outline: str,
        level2_results: list[dict[str, Any]],
        chapters: list[dict[str, Any]],
        characters: list[dict[str, Any]] | None = None,
        world_entries: list[dict[str, Any]] | None = None,
        source_index: list[dict[str, Any]] | None = None,
        extra_body: dict[str, Any] | None = None,
        require_remote: bool = True,
    ) -> dict[str, Any]:
        if require_remote:
            self.require_remote("全书分析三级草案")
        if not self.is_remote_configured():
            self.require_remote("全书分析三级草案")
        try:
            return self._analyze_book_level3_draft_remote(
                book_title=book_title,
                book_outline=book_outline,
                level2_results=level2_results,
                chapters=chapters,
                characters=characters or [],
                world_entries=world_entries or [],
                source_index=source_index or [],
                extra_body=extra_body,
            )
        except Exception as exc:
            self._remember_remote_error("全书分析三级草案", exc)
            raise

    def analyze_book_level3_finalize(
        self,
        *,
        book_title: str,
        book_outline: str,
        level2_results: list[dict[str, Any]],
        draft_payload: dict[str, Any],
        source_context: dict[str, Any],
        chapters: list[dict[str, Any]],
        characters: list[dict[str, Any]] | None = None,
        world_entries: list[dict[str, Any]] | None = None,
        extra_body: dict[str, Any] | None = None,
        require_remote: bool = True,
    ) -> dict[str, Any]:
        if require_remote:
            self.require_remote("全书分析三级原文复核")
        if not self.is_remote_configured():
            self.require_remote("全书分析三级原文复核")
        try:
            return self._analyze_book_level3_finalize_remote(
                book_title=book_title,
                book_outline=book_outline,
                level2_results=level2_results,
                draft_payload=draft_payload,
                source_context=source_context,
                chapters=chapters,
                characters=characters or [],
                world_entries=world_entries or [],
                extra_body=extra_body,
            )
        except Exception as exc:
            self._remember_remote_error("全书分析三级原文复核", exc)
            raise

    def extract_character_relationships(
        self,
        *,
        book_title: str,
        characters: list[dict[str, Any]],
        chapters: list[dict[str, Any]],
        require_remote: bool = False,
        cancel_event: Event | None = None,
    ) -> list[dict[str, str]]:
        if require_remote:
            self.require_remote("人物关系分析")
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("任务已取消")
        normalized_characters = self._relationship_named_characters(characters)
        if len(normalized_characters) < 2:
            return []
        if not self.is_remote_configured():
            if require_remote:
                self.require_remote("人物关系分析")
            return self._extract_relationships_mock(
                book_title=book_title,
                characters=normalized_characters,
                chapters=chapters,
            )
        try:
            payload = self._extract_relationships_remote(
                book_title=book_title,
                characters=normalized_characters,
                chapters=chapters,
            )
            if cancel_event and cancel_event.is_set():
                raise RuntimeError("任务已取消")
            return self._normalize_relationship_payload(payload, normalized_characters)
        except Exception as exc:
            self._remember_remote_error("人物关系分析", exc)
            if require_remote:
                raise
            return self._extract_relationships_mock(
                book_title=book_title,
                characters=normalized_characters,
                chapters=chapters,
            )

    def multi_agent_review(
        self,
        *,
        book_title: str,
        chapter_title: str,
        outline: str,
        content: str,
        truth_file: str,
        selected_skills: list[dict[str, Any]] | None = None,
        require_remote: bool = False,
        cancel_event: Event | None = None,
        template_content: str = "",
    ) -> dict[str, Any]:
        if require_remote:
            self.require_remote("长篇校验")
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("任务已取消")
        selected_skills = selected_skills or []
        if self.api_key and self.model:
            try:
                payload = self._multi_agent_review_remote(
                    book_title=book_title,
                    chapter_title=chapter_title,
                    outline=outline,
                    content=content,
                    truth_file=truth_file,
                    selected_skills=selected_skills,
                    template_content=template_content,
                )
                if cancel_event and cancel_event.is_set():
                    raise RuntimeError("任务已取消")
                return self._normalize_review_payload(payload, content, outline)
            except Exception as exc:
                self._remember_remote_error("长篇校验", exc)
                if require_remote:
                    raise
        return self._multi_agent_review_mock(book_title, chapter_title, outline, content, truth_file, selected_skills, template_content)

    def multi_agent_generate_from_outline(
        self,
        *,
        book_title: str,
        chapter_title: str,
        outline: str,
        current_content: str,
        truth_file: str,
        selected_skills: list[dict[str, Any]] | None = None,
        sourcebook_context: str = "",
        require_remote: bool = False,
        cancel_event: Event | None = None,
        template_content: str = "",
        previous_chapters: list[dict[str, Any]] | None = None,
        style_voices_block: str = "",
    ) -> dict[str, Any]:
        if require_remote:
            self.require_remote("长篇生成")
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("任务已取消")
        selected_skills = selected_skills or []
        previous_chapters = previous_chapters or []
        if self.api_key and self.model:
            try:
                payload = self._multi_agent_generate_remote(
                    book_title=book_title,
                    chapter_title=chapter_title,
                    outline=outline,
                    current_content=current_content,
                    truth_file=truth_file,
                    selected_skills=selected_skills,
                    sourcebook_context=sourcebook_context,
                    template_content=template_content,
                    previous_chapters=previous_chapters,
                    style_voices_block=style_voices_block,
                )
                if cancel_event and cancel_event.is_set():
                    raise RuntimeError("任务已取消")
                return self._normalize_review_payload(payload, current_content, outline)
            except Exception as exc:
                self._remember_remote_error("长篇生成", exc)
                if require_remote:
                    raise
        return self._multi_agent_generate_mock(
            book_title=book_title,
            chapter_title=chapter_title,
            outline=outline,
            current_content=current_content,
            truth_file=truth_file,
            selected_skills=selected_skills,
            sourcebook_context=sourcebook_context,
            template_content=template_content,
            previous_chapters=previous_chapters,
        )

    def multi_agent_graph_generate(
        self,
        *,
        book_title: str,
        chapter_title: str,
        outline: str,
        current_content: str,
        truth_file: str,
        selected_skills: list[dict[str, Any]] | None = None,
        sourcebook_context: str = "",
        require_remote: bool = False,
        cancel_event: Event | None = None,
        template_content: str = "",
        style_voices_block: str = "",
    ) -> dict[str, Any]:
        from novel_app.agents import AgentGraph, AgentState
        if require_remote:
            self.require_remote("多 Agent 图编排生成")
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("任务已取消")
        graph = AgentGraph(
            self._post_chat_completion,
            model_router=getattr(self, '_model_router', None),
            prompt_overrides=self.get_prompt_overrides(),
        )
        state = AgentState(
            book_title=book_title,
            chapter_title=chapter_title,
            outline=outline,
            current_content=current_content,
            truth_file=truth_file,
            sourcebook_context=sourcebook_context,
            template_content=template_content,
            style_voices_block=style_voices_block,
            selected_skills=selected_skills or [],
            _cancel_event=cancel_event,
        )
        state.plan = ""
        state.draft = current_content
        state = graph.run_generation(state)
        result = state.to_result()
        return self._normalize_review_payload(result, current_content, outline)

    def multi_agent_graph_review(
        self,
        *,
        book_title: str,
        chapter_title: str,
        outline: str,
        content: str,
        truth_file: str,
        selected_skills: list[dict[str, Any]] | None = None,
        require_remote: bool = False,
        cancel_event: Event | None = None,
        template_content: str = "",
    ) -> dict[str, Any]:
        from novel_app.agents import AgentGraph, AgentState
        if require_remote:
            self.require_remote("多 Agent 图编排审查")
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("任务已取消")
        graph = AgentGraph(
            self._post_chat_completion,
            model_router=getattr(self, '_model_router', None),
            prompt_overrides=self.get_prompt_overrides(),
        )
        state = AgentState(
            book_title=book_title,
            chapter_title=chapter_title,
            outline=outline,
            current_content=content,
            truth_file=truth_file,
            template_content=template_content,
            selected_skills=selected_skills or [],
            _cancel_event=cancel_event,
        )
        state = graph.run_review(state)
        result = state.to_result()
        return self._normalize_review_payload(result, content, outline)

    def _multi_agent_generate_remote(
        self,
        *,
        book_title: str,
        chapter_title: str,
        outline: str,
        current_content: str,
        truth_file: str,
        selected_skills: list[dict[str, Any]],
        sourcebook_context: str,
        template_content: str = "",
        previous_chapters: list[dict[str, Any]] | None = None,
        style_voices_block: str = "",
    ) -> dict[str, Any]:
        prev_chapters = previous_chapters or []
        prev_blocks: list[str] = []
        for i, ch in enumerate(prev_chapters, start=1):
            prev_blocks.append(
                f"=== 前序章节{i}：{ch.get('title', '未知')} ===\n"
                f"正文节选：{str(ch.get('content', ''))[:1500]}"
            )
        prev_context_block = ""
        if prev_blocks:
            prev_context_block = f"\n\n前序章节正文参考（请保持语言风格和叙事节奏一致）：\n" + "\n\n".join(prev_blocks) + "\n"
        style_block = ""
        if style_voices_block.strip():
            style_block = f"\n\n{style_voices_block.strip()}\n\n请严格按照以上风格特征、人物设定和角色声音生成正文；生成后必须检查人物动机、台词和关系是否 OOC。\n"
        prompt = (
            "请模拟一个长篇小说章节生成流水线：大纲拆解员、人物代入员、场景规划员、正文写手、剧情校验员、OOC 审查员、连续性审查员、文风修订员、最终校验员。\n"
            "目标：生成完整章节正文，并在同一流程内完成一致性、OOC 和文风校验。\n"
            "只输出 JSON 对象，不要解释。\n"
            "JSON 字段：\n"
            "- summary: 本次生成摘要\n"
            "- overall_score: 0-100 整数，越高表示越可直接写入\n"
            "- final_verdict: approve 或 reject；只有正文完整、符合大纲且可安全覆盖时才 approve\n"
            "- findings: 数组，每项含 agent, severity(high|medium|low), category, location_hint, quote, issue, suggestion；如发现人物 OOC，agent 使用 ooc_auditor\n"
            "- revised_content: 生成并经审查修订后的完整章节正文\n"
            "- revised_outline: 生成后同步修正的章节大纲；如果不需要修改则返回原大纲\n"
            "- template_comparison: 如提供对照模板，说明生成结果与模板的相似点、差异和风格偏移；否则返回空字符串\n"
            "- risk_notes: 覆盖正文前需要提醒作者的风险\n"
            "硬性规则：不要偏离当前章节大纲；不要引入 Truth File 不支持的核心设定；不要让角色做出缺少铺垫的 OOC 行为；不要输出创作过程；不要输出 Markdown 代码块；正文必须是小说正文而非提纲。\n\n"
            f"书名：{book_title or '未命名作品'}\n"
            f"章节：{chapter_title or '未命名章节'}\n"
            f"章节大纲：\n{outline or '暂无大纲'}\n\n"
            f"当前已有正文（如果有，请在其基础上整体修订；如果为空，请生成完整正文）：\n{current_content[:9000] or '空'}\n\n"
            f"启用 Skills：{self._format_skill_block(selected_skills)}\n"
            f"参考书/设定速览：\n{sourcebook_context[:4000]}\n\n"
            f"对照模板章节：\n{template_content[:3000]}\n\n"
            + prev_context_block
            + style_block
            + f"Truth File：\n{truth_file[:9000]}"
        )
        result = self._post_chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": "你是中文长篇小说的长篇生成与 OOC 校验系统，只返回指定 JSON。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.65,
        )
        raw_text = self._chat_completion_content(result, "长篇生成")
        return self._extract_json_object_payload(raw_text)

    def _multi_agent_generate_mock(
        self,
        *,
        book_title: str,
        chapter_title: str,
        outline: str,
        current_content: str,
        truth_file: str,
        selected_skills: list[dict[str, Any]],
        sourcebook_context: str,
        template_content: str = "",
        previous_chapters: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        outline_text = outline.strip() or "本章需要推进核心冲突，呈现人物选择，并留下下一章钩子。"
        base = current_content.strip()
        if base:
            content = re.sub(r"\n{3,}", "\n\n", base)
            content = f"{content}\n\n【多智能体修订】本章已根据大纲完成结构复核，建议继续补强人物动机、场景目标和结尾钩子。"
        else:
            content = (
                f"{chapter_title or '本章'}\n\n"
                f"{outline_text}\n\n"
                "夜色像一层缓慢落下的幕布，把所有未说出口的话都压进沉默里。主角站在门前，意识到这一章真正要解决的并不是眼前的阻碍，而是自己一直回避的选择。\n\n"
                "他先确认目标，再审视代价。每一个动作都被环境放大：脚步声、风声、远处若有若无的呼喊，都在提醒他，故事已经不能再停在原地。\n\n"
                "冲突随之逼近。对手并没有立刻现身，却通过留下的痕迹改变了局面。主角必须在保守退让和冒险推进之间做出判断，而这个判断也会改变人物关系与后续剧情。\n\n"
                "最终，他选择向前。这个决定暂时解决了眼前问题，却也打开了更深的疑问：真正的危险并不在门后，而在所有人都以为已经确定的设定之中。"
            )
        prev_ctx_note = f"（已参考 {len(previous_chapters or [])} 个前序章节）" if (previous_chapters and len(previous_chapters) > 0) else ""
        payload = {
            "summary": f"《{book_title or '未命名作品'}》/{chapter_title or '当前章节'} 已完成本地长篇生成兜底{prev_ctx_note}。",
            "overall_score": 64,
            "final_verdict": "approve",
            "findings": [
                {
                    "agent": "ooc_auditor",
                    "severity": "low",
                    "category": "人物代入",
                    "location_hint": "全章",
                    "quote": outline_text[:120],
                    "issue": "本地 Mock 已加入人物代入与 OOC 检查占位，但无法替代远程模型的细粒度角色判断。",
                    "suggestion": "接入远程长篇生成用途模型后，可获得更稳定的人物口吻、动机和关系一致性检查。",
                }
            ],
            "revised_content": content,
            "revised_outline": outline_text,
            "template_comparison": "本地 Mock 已读取对照模板上下文；真实远程模型会进一步比较节奏、对白密度和描写比例。" if template_content.strip() else "",
            "risk_notes": "本地 Mock 只提供结构兜底，不代表真实长篇生成质量。",
        }
        return self._normalize_review_payload(payload, current_content, outline)

    def _multi_agent_review_remote(
        self,
        *,
        book_title: str,
        chapter_title: str,
        outline: str,
        content: str,
        truth_file: str,
        selected_skills: list[dict[str, Any]],
        template_content: str = "",
    ) -> dict[str, Any]:
        prompt = (
            "请模拟一个多智能体小说审查流水线：上下文整理器、剧情审查员、连续性审查员、文风审查员、修订智能体、最终校验员。\n"
            "只输出 JSON 对象，不要解释。\n"
            "JSON 字段：\n"
            "- summary: 本次审查摘要\n"
            "- overall_score: 0-100 整数，越高表示越可直接发布\n"
            "- final_verdict: approve 或 reject；只有修订后正文可安全覆盖原文时才 approve\n"
            "- findings: 数组，每项含 agent, severity(high|medium|low), category, location_hint, quote, issue, suggestion\n"
            "- revised_content: 修订后的完整正文；如果 reject，也要给出保守修订草稿\n"
            "- revised_outline: 修订后的章节大纲；如果不需要修改则返回原大纲\n"
            "- template_comparison: 如提供对照模板，说明当前正文与模板的相似点、差异和风格偏移；否则返回空字符串\n"
            "- risk_notes: 覆盖正文前需要提醒作者的风险\n"
            "审查规则：不要改变核心剧情事实；不要引入 Truth File 中没有支撑的设定；不要删除作者独特风格；优先修复矛盾、重复、节奏断裂和不清晰表达。\n\n"
            f"书名：{book_title or '未命名作品'}\n"
            f"章节：{chapter_title or '未命名章节'}\n"
            f"当前大纲：{outline or '暂无大纲'}\n"
            f"启用 Skills：{self._format_skill_block(selected_skills)}\n"
            f"对照模板章节：\n{template_content[:3000]}\n\n"
            f"Truth File：\n{truth_file[:9000]}\n\n"
            f"原正文：\n{content[:16000]}"
        )
        result = self._post_chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": "你是中文长篇小说的长篇校验与修订系统，只返回指定 JSON。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.25,
        )
        raw_text = self._chat_completion_content(result, "长篇审查")
        return self._extract_json_object_payload(raw_text)

    def _multi_agent_review_mock(
        self,
        book_title: str,
        chapter_title: str,
        outline: str,
        content: str,
        truth_file: str,
        selected_skills: list[dict[str, Any]],
        template_content: str = "",
    ) -> dict[str, Any]:
        cleaned = content.strip()
        if cleaned:
            revised = re.sub(r"\n{3,}", "\n\n", cleaned)
        else:
            revised = f"{chapter_title or '本章'}围绕既定大纲展开，先补足场景目标，再推进人物选择。"
        if revised == cleaned and len(revised) >= 80:
            revised = f"{revised}\n\n【校验修订】本段已按长篇校验流程完成一次保守整理，建议作者继续检查人物动机与前后设定。"
        elif revised == cleaned:
            revised = f"{revised}\n\n【审查修订】建议继续补充场景、冲突和人物反应。".strip()
        findings = [
            {
                "agent": "plot_auditor",
                "severity": "medium" if len(cleaned) < 800 else "low",
                "category": "剧情推进",
                "location_hint": "全章",
                "quote": cleaned[:80],
                "issue": "本地审查提示：当前章节仍需要确认冲突推进是否足够清晰。",
                "suggestion": "检查每个场景是否有目标、阻力和结果，必要时补一两句人物反应。",
            },
            {
                "agent": "continuity_auditor",
                "severity": "low",
                "category": "连续性",
                "location_hint": "Truth File",
                "quote": "",
                "issue": "已按当前人物、世界观和大纲做一致性兜底检查。",
                "suggestion": "如果后续接入远程审查模型，可获得更细的矛盾定位。",
            },
        ]
        payload = {
            "summary": f"《{book_title or '未命名作品'}》/{chapter_title or '当前章节'} 已完成本地长篇校验兜底。",
            "overall_score": 72 if len(cleaned) >= 800 else 58,
            "final_verdict": "approve",
            "findings": findings,
            "revised_content": revised,
            "revised_outline": outline.strip() or "本章需围绕当前冲突推进，并保持人物动机、设定和节奏一致。",
            "template_comparison": "本地 Mock 已读取对照模板；建议远程审查时重点比较叙事节奏、对白密度和段落长度。" if template_content.strip() else "",
            "risk_notes": "本地 Mock 只做结构兜底，不代表真实模型审查质量。",
        }
        return self._normalize_review_payload(payload, content, outline)

    def _normalize_review_payload(self, payload: dict[str, Any], fallback_content: str, fallback_outline: str) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("Review payload must be a JSON object.")
        findings: list[dict[str, str]] = []
        raw_findings = payload.get("findings", [])
        if isinstance(raw_findings, list):
            for item in raw_findings[:40]:
                if not isinstance(item, dict):
                    continue
                severity = str(item.get("severity", "low")).strip().lower()
                if severity not in {"high", "medium", "low"}:
                    severity = "low"
                issue = str(item.get("issue") or item.get("issue_text") or "").strip()
                suggestion = str(item.get("suggestion") or item.get("suggestion_text") or "").strip()
                if not issue and not suggestion:
                    continue
                findings.append(
                    {
                        "agent": str(item.get("agent", "")).strip()[:80],
                        "severity": severity,
                        "category": str(item.get("category", "")).strip()[:80],
                        "location_hint": str(item.get("location_hint", "")).strip()[:160],
                        "quote": str(item.get("quote") or item.get("quote_text") or "").strip()[:600],
                        "issue": issue[:1000],
                        "suggestion": suggestion[:1000],
                    }
                )
        verdict_raw = payload.get("final_verdict", payload.get("verdict", "reject"))
        if isinstance(verdict_raw, bool):
            final_verdict = "approve" if verdict_raw else "reject"
        else:
            verdict_text = str(verdict_raw).strip().lower()
            final_verdict = "approve" if verdict_text in {"approve", "approved", "pass", "passed", "ok", "true"} else "reject"
        revised_content = str(payload.get("revised_content") or payload.get("content") or "").strip()
        revised_outline = str(payload.get("revised_outline") or payload.get("outline") or "").strip()
        if not revised_content:
            final_verdict = "reject"
            revised_content = fallback_content
            findings.insert(
                0,
                {
                    "agent": "safety_gate",
                    "severity": "high",
                    "category": "安全护栏",
                    "location_hint": "revised_content",
                    "quote": "",
                    "issue": "模型返回的修订正文为空，已阻止自动覆盖。",
                    "suggestion": "请重新校验，或在生成记录中人工比对后再决定是否手动应用。",
                },
            )
        fallback_length = len(fallback_content.strip())
        if final_verdict == "approve" and fallback_length >= 200 and len(revised_content.strip()) < int(fallback_length * 0.4):
            final_verdict = "reject"
            findings.insert(
                0,
                {
                    "agent": "safety_gate",
                    "severity": "high",
                    "category": "安全护栏",
                    "location_hint": "revised_content",
                    "quote": "",
                    "issue": "模型返回的修订正文长度异常缩短，已阻止自动覆盖。",
                    "suggestion": "请重新校验或手动比对生成记录中的草稿后再决定是否应用。",
                },
            )
        findings = findings[:40]
        if not revised_outline:
            revised_outline = fallback_outline
        risk_notes = payload.get("risk_notes", "")
        if isinstance(risk_notes, list):
            risk_notes = "\n".join(str(item).strip() for item in risk_notes if str(item).strip())
        template_comparison = payload.get("template_comparison", "")
        if isinstance(template_comparison, list):
            template_comparison = "\n".join(str(item).strip() for item in template_comparison if str(item).strip())
        return {
            "summary": str(payload.get("summary", "")).strip(),
            "overall_score": self._coerce_probability(payload.get("overall_score", 0)),
            "final_verdict": final_verdict,
            "findings": findings,
            "revised_content": revised_content,
            "revised_outline": revised_outline,
            "template_comparison": str(template_comparison).strip()[:3000],
            "risk_notes": str(risk_notes).strip(),
        }

    def cross_chapter_check(
        self,
        *,
        current_chapter_title: str,
        current_chapter_content: str,
        previous_chapters: list[dict[str, Any]],
        truth_file: str,
        require_remote: bool = False,
        cancel_event: Any = None,
    ) -> dict[str, Any]:
        if require_remote:
            self.require_remote("跨章节一致性检查")
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("任务已取消")
        if len(previous_chapters) == 0:
            return {"cross_findings": [], "cross_summary": ""}
        if not (self.api_key and self.model):
            return self._cross_chapter_check_mock(
                current_chapter_title=current_chapter_title,
                current_chapter_content=current_chapter_content,
                previous_chapters=previous_chapters,
                truth_file=truth_file,
            )
        try:
            payload = self._cross_chapter_check_remote(
                current_chapter_title=current_chapter_title,
                current_chapter_content=current_chapter_content,
                previous_chapters=previous_chapters,
                truth_file=truth_file,
            )
            if cancel_event and cancel_event.is_set():
                raise RuntimeError("任务已取消")
            return self._normalize_cross_chapter_payload(payload)
        except Exception as exc:
            self._remember_remote_error("跨章节一致性检查", exc)
            if require_remote:
                raise
        return self._cross_chapter_check_mock(
            current_chapter_title=current_chapter_title,
            current_chapter_content=current_chapter_content,
            previous_chapters=previous_chapters,
            truth_file=truth_file,
        )

    def _cross_chapter_check_remote(
        self,
        *,
        current_chapter_title: str,
        current_chapter_content: str,
        previous_chapters: list[dict[str, Any]],
        truth_file: str,
    ) -> dict[str, Any]:
        prev_blocks: list[str] = []
        for i, ch in enumerate(previous_chapters, start=1):
            prev_blocks.append(
                f"=== 前序章节{i}：{ch.get('title', '未知')} ===\n"
                f"正文：{str(ch.get('content', ''))[:2500]}"
            )
        prompt = (
            "你是中文长篇小说的跨章节一致性审查员。\n"
            "只输出 JSON 对象，不要解释。\n"
            "JSON 字段：\n"
            "- cross_summary: 跨章节一致性总体评估（100字以内）\n"
            "- cross_findings: 数组，每项含 dimension(character|world|fact), severity(high|medium|low), conflict_with(冲突章节名), issue(问题描述), suggestion(修订建议)\n"
            "检查维度：\n"
            "  - character: 人物状态不一致（外貌/性格/关系/位置/能力等）\n"
            "  - world: 世界观设定冲突（地理/规则/社会结构/历史等）\n"
            "  - fact: 剧情事实矛盾（事件顺序/细节/因果关系等）\n"
            "如果当前章节与所有前序章节均保持一致，cross_findings 返回空数组。\n\n"
            f"当前章节：{current_chapter_title or '未知'}\n"
            f"当前章节正文：\n{current_chapter_content[:5000]}\n\n"
            f"前序章节（{len(previous_chapters)}章）：\n"
            + "\n\n".join(prev_blocks)
            + f"\n\nTruth File：\n{truth_file[:6000]}"
        )
        result = self._post_chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": "你是中文长篇小说的跨章节一致性审查系统，只返回指定 JSON。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.25,
        )
        raw_text = self._chat_completion_content(result, "跨章节一致性审查")
        return self._extract_json_object_payload(raw_text)

    def _cross_chapter_check_mock(
        self,
        *,
        current_chapter_title: str,
        current_chapter_content: str,
        previous_chapters: list[dict[str, Any]],
        truth_file: str,
    ) -> dict[str, Any]:
        return {
            "cross_findings": [],
            "cross_summary": f"本地 Mock：已参考 {len(previous_chapters)} 个前序章节，未检测到明显不一致。",
        }

    def _normalize_cross_chapter_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        findings: list[dict[str, str]] = []
        raw_findings = payload.get("cross_findings", [])
        if isinstance(raw_findings, list):
            for item in raw_findings[:30]:
                if not isinstance(item, dict):
                    continue
                dimension = str(item.get("dimension", "")).strip()
                if dimension not in {"character", "world", "fact"}:
                    continue
                severity = str(item.get("severity", "medium")).strip().lower()
                if severity not in {"high", "medium", "low"}:
                    severity = "medium"
                issue = str(item.get("issue", "")).strip()
                if not issue:
                    continue
                findings.append({
                    "agent": "cross_chapter_auditor",
                    "severity": severity,
                    "category": f"跨章节-{dimension}",
                    "location_hint": str(item.get("conflict_with", "")).strip()[:80],
                    "quote": "",
                    "issue": issue[:800],
                    "suggestion": str(item.get("suggestion", "")).strip()[:800],
                    "dimension": dimension,
                    "conflict_with": str(item.get("conflict_with", "")).strip()[:80],
                    "is_cross_chapter": True,
                })
        return {
            "cross_findings": findings,
            "cross_summary": str(payload.get("cross_summary", "")).strip()[:500],
        }

    def extract_style_profile(
        self,
        *,
        sample_texts: list[str],
        require_remote: bool = False,
    ) -> dict[str, Any]:
        if require_remote:
            self.require_remote("风格特征提取")
        if not sample_texts:
            return {"style_profile": ""}
        combined = "\n\n---\n\n".join(t[:3000] for t in sample_texts if t.strip())
        if not combined.strip():
            return {"style_profile": ""}
        self.require_remote("风格特征提取")
        try:
            payload = self._extract_style_profile_remote(combined)
            return payload
        except Exception as exc:
            self._remember_remote_error("风格特征提取", exc)
            raise

    def _extract_style_profile_remote(self, combined_text: str) -> dict[str, Any]:
        prompt = (
            "分析以下小说文本的写作风格特征，只输出 JSON 对象，不要解释。\n"
            "JSON 字段：\n"
            "- narrative_perspective: 叙事视角（第一人称/第三人称有限/第三人称全知/第二人称）\n"
            "- dialogue_density: 对话密度（高/中/低）\n"
            "- description_ratio: 描写占比（高/中/低）\n"
            "- avg_paragraph_length: 段落平均长度（短<50字/中50-150字/长>150字）\n"
            "- tone: 整体基调（如：沉稳/轻快/压抑/幽默/冷峻）\n"
            "- vocabulary_level: 词汇风格（口语化/书面化/文学化）\n"
            "- pacing: 叙事节奏（快/中/慢）\n"
            "- style_notes: 风格要点总结（200字以内）\n\n"
            f"待分析文本：\n{combined_text[:8000]}"
        )
        result = self._post_chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": "你是小说风格分析专家，只返回指定 JSON。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.15,
        )
        raw_text = self._chat_completion_content(result, "风格分析")
        payload = self._extract_json_object_payload(raw_text)
        profile_parts = []
        fields = [
            ("narrative_perspective", "叙事视角"),
            ("dialogue_density", "对话密度"),
            ("description_ratio", "描写占比"),
            ("avg_paragraph_length", "段落长度"),
            ("tone", "基调"),
            ("vocabulary_level", "词汇风格"),
            ("pacing", "节奏"),
        ]
        for key, label in fields:
            val = str(payload.get(key, "")).strip()
            if val:
                profile_parts.append(f"{label}：{val}")
        notes = str(payload.get("style_notes", "")).strip()
        if notes:
            profile_parts.append(f"要点：{notes}")
        return {"style_profile": "；".join(profile_parts) if profile_parts else ""}

    def extract_character_voices(
        self,
        *,
        chapters: list[dict[str, Any]],
        character_names: list[str] | None = None,
        require_remote: bool = False,
    ) -> dict[str, Any]:
        if require_remote:
            self.require_remote("角色声音提取")
        if not chapters:
            return {"character_voices": []}
        self.require_remote("角色声音提取")
        try:
            payload = self._extract_character_voices_remote(chapters, character_names)
            return payload
        except Exception as exc:
            self._remember_remote_error("角色声音提取", exc)
            raise

    def _extract_character_voices_remote(
        self,
        chapters: list[dict[str, Any]],
        character_names: list[str] | None,
    ) -> dict[str, Any]:
        chapter_blocks: list[str] = []
        for ch in chapters[:5]:
            title = str(ch.get("title", "未知"))
            content = str(ch.get("content", ""))[:2000]
            chapter_blocks.append(f"=== {title} ===\n{content}")
        combined = "\n\n".join(chapter_blocks)
        names_hint = ""
        if character_names:
            names_hint = f"\n重点关注角色：{'、'.join(character_names[:10])}"
        prompt = (
            "从以下小说章节中提取主要角色的说话风格特征，只输出 JSON 对象，不要解释。\n"
            "JSON 字段：\n"
            "- character_voices: 数组，每项含 name(角色名), speech_style(说话风格：如简短有力/絮叨/文雅/粗犷), "
            "catchwords(口头禅或高频用词，逗号分隔), personality_hint(性格提示，20字以内)\n"
            "- 最多提取 8 个角色，只提取有对话或明确行为描写的角色\n"
            "- 如果无法确定角色说话风格，speech_style 填\"未明确\"\n\n"
            f"待分析章节：\n{combined[:8000]}"
            + names_hint
        )
        result = self._post_chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": "你是小说角色分析专家，只返回指定 JSON。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.15,
        )
        raw_text = self._chat_completion_content(result, "角色声音分析")
        payload = self._extract_json_object_payload(raw_text)
        voices = payload.get("character_voices", [])
        if not isinstance(voices, list):
            voices = []
        valid_voices = []
        for v in voices[:8]:
            if not isinstance(v, dict):
                continue
            name = str(v.get("name", "")).strip()
            if not name:
                continue
            valid_voices.append({
                "name": name,
                "speech_style": str(v.get("speech_style", "未明确")).strip()[:40],
                "catchwords": str(v.get("catchwords", "")).strip()[:100],
                "personality_hint": str(v.get("personality_hint", "")).strip()[:40],
            })
        return {"character_voices": valid_voices}

    def format_style_and_voices_block(
        self,
        style_profile: str,
        character_voices: list[dict[str, Any]],
    ) -> str:
        parts: list[str] = []
        if style_profile.strip():
            parts.append(f"【写作风格特征】{style_profile.strip()}")
        if character_voices:
            voice_lines = []
            for v in character_voices[:8]:
                name = str(v.get("name", ""))
                style = str(v.get("speech_style", ""))
                catchwords = str(v.get("catchwords", ""))
                hint = str(v.get("personality_hint", ""))
                line = f"- {name}：说话风格「{style}」"
                if catchwords:
                    line += f"，口头禅「{catchwords}」"
                if hint:
                    line += f"，{hint}"
                voice_lines.append(line)
            parts.append("【角色声音卡片】\n" + "\n".join(voice_lines))
        return "\n\n".join(parts) if parts else ""

    def _analyze_book_level1_remote(
        self,
        *,
        book_title: str,
        book_outline: str,
        chunk_text: str,
        chunk_index: int,
        total_chunks: int,
        chunk_id: str = "",
        chapter_ids: list[int] | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        chapter_ids = chapter_ids or []
        evidence_context = (
            "\n\n【证据输出要求】\n"
            f"- 本片段 chunk_id={chunk_id or f'chunk-{chunk_index:04d}'}，覆盖 chapter_ids={json.dumps(chapter_ids, ensure_ascii=False)}。\n"
            "- 所有事实、人物线索、世界观线索、冲突和疑问都要尽量写入 source_facts。\n"
            "- source_facts 每项字段：fact_id、chapter_id、chunk_id、category、subject、claim、evidence_quote、confidence、uncertainty。\n"
            "- evidence_quote 必须是原文短引或极近似短句；没有证据就写入 uncertainty，不要补成事实。\n"
        )
        prompt = (
            "你正在执行三级全书分析的第一级。请直接解读给定原文片段，尽可能保持原文含义，但要精简。\n"
            "只输出 JSON 对象，不要解释，不要写 Markdown。\n"
            "JSON 字段：\n"
            "- level: 固定为 1\n"
            "- chunk_index: 当前片段序号\n"
            "- total_chunks: 片段总数\n"
            "- faithful_digest: 对原文含义的忠实精简解读，保留关键因果、转折和情绪推进\n"
            "- key_events: 关键事件短句数组\n"
            "- character_clues: 数组，每项 name, role_hint, motivation, change\n"
            "- world_clues: 数组，每项 category, content\n"
            "- chapter_updates: 数组，每项 chapter_id, outline, events\n"
            "不要发明原文没有的信息；不确定时写入 uncertainty 字段。\n\n"
            f"书名：{book_title}\n"
            f"已有书籍级设定：{book_outline[:5000]}\n"
            f"当前片段：{chunk_index}/{total_chunks}\n"
            f"片段内容：\n{chunk_text}"
        )
        prompt += evidence_context
        result = self._post_chat_completion(
            messages=[
                {"role": "system", "content": "你是中文长篇小说的第一级忠实解读器，只返回指定 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.15,
            extra_body=extra_body,
        )
        raw_text = self._chat_completion_content(result, "全书分析一级")
        payload = self._extract_json_object_payload(raw_text)
        payload.setdefault("level", 1)
        payload.setdefault("chunk_index", chunk_index)
        payload.setdefault("total_chunks", total_chunks)
        payload.setdefault("chunk_id", chunk_id or f"chunk-{chunk_index:04d}")
        payload.setdefault("chapter_ids", chapter_ids)
        return payload

    def _analyze_book_level2_remote(
        self,
        *,
        book_title: str,
        level1_results: list[dict[str, Any]],
        group_index: int,
        total_groups: int,
        extra_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        prompt = (
            "你正在执行三级全书分析的第二级。请整合若干个第一级解读结果，概括内容、完善逻辑链条，理解故事走向，"
            "为第三级模板输出做准备。\n"
            "只输出 JSON 对象，不要解释，不要写 Markdown。\n"
            "JSON 字段：\n"
            "- level: 固定为 2\n"
            "- group_index: 当前二级分组序号\n"
            "- total_groups: 二级分组总数\n"
            "- story_summary: 本组故事概括\n"
            "- logic_chain: 因果链条短句数组\n"
            "- timeline: 时间线/阶段推进数组\n"
            "- character_arcs: 数组，每项 name, role, goal, conflict, change, final_state\n"
            "- world_model: 数组，每项 category, rule, evidence\n"
            "- chapter_updates: 数组，每项 chapter_id, outline, ai_probability, ai_probability_level, events\n"
            "- output_hints: 给第三级填写模板时必须保留的要点数组\n"
            "请控制输出体积：story_summary 800 字以内；logic_chain/timeline 各不超过 12 条；"
            "consolidated_facts 不超过 24 条；chapter_updates 不超过 40 条；不要复述第一级全文。\n"
            "JSON 必须严格合法：数组元素、对象字段之间必须有英文逗号；字符串内不要直接换行。\n"
            "请去重、纠错、合并同名人物和同类设定，但不要创造没有依据的新设定。\n\n"
            f"书名：{book_title}\n"
            f"二级分组：{group_index}/{total_groups}\n"
            f"第一级结果：\n{json.dumps(level1_results, ensure_ascii=False)}"
        )
        prompt += (
            "\n\n【证据保真要求】\n"
            "- 保留一级 source_facts 中的 fact_id、chapter_id、chunk_id、evidence_quote，不要把证据来源抹掉。\n"
            "- 输出 consolidated_facts，每项含 fact_ids、chapter_ids、chunk_ids、claim、evidence_quotes、confidence。\n"
            "- 对冲突信息输出 conflicts；对证据不足但三级需要判断的字段输出 coverage_gaps。\n"
            "- 不要用类型常识补全剧情、人物动机或世界观规则。\n"
        )
        result = self._post_chat_completion(
            messages=[
                {"role": "system", "content": "你是中文长篇小说的第二级结构整理器，只返回指定 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.15,
            extra_body=extra_body,
        )
        raw_text = self._chat_completion_content(result, "全书分析二级")
        payload = self._extract_json_object_payload(raw_text)
        payload.setdefault("level", 2)
        payload.setdefault("group_index", group_index)
        payload.setdefault("total_groups", total_groups)
        return payload

    def _analyze_book_level3_draft_remote(
        self,
        *,
        book_title: str,
        book_outline: str,
        level2_results: list[dict[str, Any]],
        chapters: list[dict[str, Any]],
        characters: list[dict[str, Any]],
        world_entries: list[dict[str, Any]],
        source_index: list[dict[str, Any]] | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        source_index = source_index or []
        chapter_refs = [
            {
                "id": item.get("id"),
                "title": item.get("title", ""),
                "outline": item.get("outline", ""),
            }
            for item in chapters
        ]
        prompt = (
            "你正在执行三级全书分析的第三级。请整合全部第二级结果，完全理解故事，并直接负责最终输出。\n"
            "只输出 JSON 对象，不要解释。最终结果将直接覆盖用户现有书籍级、世界观、人物卡和章节分析字段，"
            "所以请按模板谨慎填写，不要输出空壳。\n"
            "JSON 字段：\n"
            "- book_outline: 字符串，可为 Markdown 补充说明\n"
            "- book_outline_form: 对象，格式为 {fields:{字段ID:{checked/value}}, volume_plans:[{volume_id,volume_title,fields:{core_events/stage_goal/character_appearances/main_conflict/key_turning/ending_hook:{value}}}], supplements:[{title,content}]}\n"
            "- world_form: 对象，格式为 {fields:{字段ID:{checked/value}}, supplements:[{title,content}]}\n"
            "- characters: 数组，每项 name, role, profile_form 或 profile_data；必要时可附 profile_text\n"
            "- chapter_updates: 数组，每项 chapter_id, outline, ai_probability, ai_probability_level, events\n"
            "ai_probability_level 只能是 certain/high/medium/low/none。events 是本章关键事件短标签数组。\n"
            "复选框字段必须明确 checked；文本字段必须明确 value。AI 结果会覆盖旧值，所以不要省略已判断出的字段。\n\n"
            "模板骨架：\n"
            f"【书籍大纲模板】\n{book_outline_template(book_title)[:2600]}\n\n"
            f"【世界观设定模板】\n{WORLD_TEMPLATE[:2200]}\n\n"
            f"【主角设定模板】\n{PROTAGONIST_TEMPLATE[:2200]}\n\n"
            f"【配角设定模板】\n{SUPPORTING_CHARACTER_TEMPLATE[:1800]}\n\n"
            f"书名：{book_title}\n"
            f"当前书籍级设定：{book_outline[:4000]}\n"
            f"现有人物：{json.dumps(characters[:80], ensure_ascii=False)}\n"
            f"现有世界观：{json.dumps(world_entries[:40], ensure_ascii=False)}\n"
            f"章节索引：{json.dumps(chapter_refs, ensure_ascii=False)}\n"
            f"第二级结果：\n{json.dumps(level2_results, ensure_ascii=False)}"
        )
        prompt += (
            "\n\n【第三级草案与回查要求】\n"
            "- 你现在先产出可写回草案，同时审查证据是否足够；不要把猜测写成模板字段。\n"
            "- 所有写入 book_outline_form、world_form、characters.profile_form、chapter_updates 的字段，都尽量附 evidence_refs 或 source_quotes。\n"
            "- 复选框 checked 只有在二级事实或原文证据明确支持时才为 true；无法判断保持 false 或留空。\n"
            "- 如遇存疑、冲突、证据不足、字段难以判断，请输出 source_requests 数组。\n"
            "- source_requests 每项含 request_id、reason、target_field、chapter_id、chunk_id、keywords。\n"
            "- 无证据但需要人工确认的问题写入 analysis_unresolved，不要写入 Truth/RAG 内容字段。\n"
            f"\n【本次可回查原文索引】\n{json.dumps(source_index[:120], ensure_ascii=False)}"
        )
        result = self._post_chat_completion(
            messages=[
                {"role": "system", "content": "你是中文长篇小说项目的第三级终审分析器，只返回最终 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=None,
            extra_body=extra_body,
        )
        raw_text = self._chat_completion_content(result, "全书分析三级草案")
        payload = self._extract_json_object_payload(raw_text)
        return payload

    def _analyze_book_level3_remote(
        self,
        *,
        book_title: str,
        book_outline: str,
        level2_results: list[dict[str, Any]],
        chapters: list[dict[str, Any]],
        characters: list[dict[str, Any]],
        world_entries: list[dict[str, Any]],
        extra_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._analyze_book_level3_draft_remote(
            book_title=book_title,
            book_outline=book_outline,
            level2_results=level2_results,
            chapters=chapters,
            characters=characters,
            world_entries=world_entries,
            source_index=[],
            extra_body=extra_body,
        )

    def _analyze_book_level3_finalize_remote(
        self,
        *,
        book_title: str,
        book_outline: str,
        level2_results: list[dict[str, Any]],
        draft_payload: dict[str, Any],
        source_context: dict[str, Any],
        chapters: list[dict[str, Any]],
        characters: list[dict[str, Any]],
        world_entries: list[dict[str, Any]],
        extra_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        chapter_refs = [
            {
                "id": item.get("id"),
                "title": item.get("title", ""),
                "outline": item.get("outline", ""),
            }
            for item in chapters
        ]
        prompt = (
            "你是三级全书分析的最终复核器。请根据二级结果、三级草案和本地回查到的原文片段，输出最终可写回 JSON。\n"
            "只返回 JSON 对象，不要解释，不要 Markdown 包裹。\n"
            "必须遵守：\n"
            "- 字段写入只能来自二级事实或 source_context 原文片段；不要用类型常识、网文套路或模板默认值补空。\n"
            "- 草案中没有证据的字段需要删除或留空；无法解决的问题写入 analysis_unresolved。\n"
            "- 复选框 checked 只有在原文/二级事实明确支持时才为 true。\n"
            "- 人物卡重点核实身份、性格、动机、能力、关系线；世界观重点核实规则、时代、势力、地理、危机；书籍级重点核实题材、结构、主题、爽点/虐点、分卷规划。\n"
            "- 输出字段仍为 book_outline、book_outline_form、world_form、characters、chapter_updates、analysis_unresolved。\n"
            "- 每个非空 value 或 checked=true 的字段尽量保留 evidence_refs 或 source_quotes。\n\n"
            f"书名：{book_title}\n"
            f"当前书籍级设定：{book_outline[:4000]}\n"
            f"现有人物：{json.dumps(characters[:80], ensure_ascii=False)}\n"
            f"现有世界观：{json.dumps(world_entries[:40], ensure_ascii=False)}\n"
            f"章节索引：{json.dumps(chapter_refs, ensure_ascii=False)}\n"
            f"第二级结果：\n{json.dumps(level2_results, ensure_ascii=False)}\n\n"
            f"三级草案：\n{json.dumps(draft_payload, ensure_ascii=False)}\n\n"
            f"回查原文片段：\n{json.dumps(source_context, ensure_ascii=False)}"
        )
        result = self._post_chat_completion(
            messages=[
                {"role": "system", "content": "你是中文长篇小说项目的第三级原文复核与模板精填器，只返回最终 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=None,
            extra_body=extra_body,
        )
        raw_text = self._chat_completion_content(result, "全书分析三级原文复核")
        payload = self._extract_json_object_payload(raw_text)
        return payload

    def _analyze_book_remote(
        self,
        *,
        book_title: str,
        book_outline: str,
        chapters: list[dict[str, Any]],
        characters: list[dict[str, Any]],
        world_entries: list[dict[str, Any]],
    ) -> dict[str, Any]:
        MAX_INPUT_CHARS = 80000
        overhead = len(book_title) + len(book_outline) + len(json.dumps(characters[:40], ensure_ascii=False)) + len(json.dumps(world_entries[:40], ensure_ascii=False)) + 3000
        available = max(1000, MAX_INPUT_CHARS - overhead)
        max_chapters = min(len(chapters), 80)
        per_chapter_limit = max(500, min(2200, available // max(1, max_chapters)))
        chapter_payload = []
        for item in chapters[:max_chapters]:
            chapter_payload.append(
                {
                    "id": item.get("id"),
                    "title": item.get("title", ""),
                    "outline": item.get("outline", ""),
                    "content": str(item.get("content", ""))[:per_chapter_limit],
                }
            )
        prompt = (
            "请分析这部长篇小说项目，只输出 JSON 对象，不要解释。\n"
            "JSON 字段：\n"
            "- book_outline: 字符串，必须是 Markdown，并按照【书籍大纲模板】补全；用户已填写的字段要作为硬约束保留\n"
            "- book_outline_form: 可选对象，格式为 {fields:{字段ID:{checked/value}}, volume_plans:[{volume_id,volume_title,fields:{core_events/stage_goal/character_appearances/main_conflict/key_turning/ending_hook:{value}}}], supplements:[{title,content}]}；只填写高置信度字段\n"
            "- world_form: 可选对象，格式为 {fields:{字段ID:{checked/value}}, supplements:[{title,content}]}；只填写高置信度字段\n"
            "- characters: 数组，每项 name, role, profile_text；profile_text 必须是 Markdown，主角按【主角设定模板】，其他人物按【配角设定模板】补全\n"
            "- world_entries: 兼容字段，可为空；优先使用 world_form 表达世界观\n"
            "- chapter_updates: 数组，每项 chapter_id, outline, ai_probability, ai_probability_level, events\n"
            "分级 ai_probability_level 只能是 certain/high/medium/low/none。\n"
            "events 是本章关键事件短标签数组。\n\n"
            "模板骨架：\n"
            f"【书籍大纲模板】\n{book_outline_template(book_title)[:2600]}\n\n"
            f"【世界观设定模板】\n{WORLD_TEMPLATE[:2200]}\n\n"
            f"【主角设定模板】\n{PROTAGONIST_TEMPLATE[:2200]}\n\n"
            f"【配角设定模板】\n{SUPPORTING_CHARACTER_TEMPLATE[:1800]}\n\n"
            f"书名：{book_title}\n"
            f"书籍大纲：{book_outline[:4000]}\n"
            f"现有人物：{json.dumps(characters[:40], ensure_ascii=False)}\n"
            f"现有世界观：{json.dumps(world_entries[:40], ensure_ascii=False)}\n"
            f"章节：{json.dumps(chapter_payload, ensure_ascii=False)}"
        )
        result = self._post_chat_completion(
            messages=[
                {"role": "system", "content": "你是中文长篇小说项目分析器，擅长抽取人物、世界观、章节大纲和关键事件，只返回 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.25,
        )
        raw_text = self._chat_completion_content(result, "全书分析")
        payload = self._extract_json_object_payload(raw_text)
        return payload

    def _analyze_book_mock(
        self,
        book_title: str,
        book_outline: str,
        chapters: list[dict[str, Any]],
        characters: list[dict[str, Any]],
        world_entries: list[dict[str, Any]],
    ) -> dict[str, Any]:
        chapter_updates: list[dict[str, Any]] = []
        outline_lines = [f"全书分析：{book_title or '未命名作品'}"]
        if book_outline.strip():
            outline_lines.append(book_outline.strip()[:600])
        outline_lines.append(f"规模：{len(chapters)} 章")
        for item in chapters[:80]:
            content = str(item.get("content", ""))
            outline = str(item.get("outline", "")).strip()
            if not outline:
                first_line = next((line.strip() for line in content.splitlines() if line.strip()), "")
                outline = f"本章围绕「{first_line[:36] or item.get('title', '章节')}」推进。"
            outline_lines.append(f"- {item.get('title', '章节')}：{outline.splitlines()[0][:80]}")
            chapter_updates.append(
                {
                    "chapter_id": item.get("id"),
                    "outline": outline,
                    "ai_probability": int(item.get("ai_probability", 0) or 0),
                    "ai_probability_level": str(item.get("ai_probability_level", "none") or "none"),
                    "events": [str(item.get("title", "章节"))[:24]],
                }
            )
        return {
            "book_outline": "\n".join(outline_lines[:90]),
            "characters": characters,
            "world_entries": world_entries,
            "chapter_updates": chapter_updates,
        }

    def _relationship_named_characters(self, characters: list[dict[str, Any]]) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in characters:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "") or "").strip()
            if not name:
                continue
            key = re.sub(r"\s+", "", name).casefold()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(
                {
                    "name": name[:60],
                    "role": str(item.get("role", "") or "").strip()[:80],
                    "profile_text": str(item.get("profile_text", "") or item.get("profile", "") or "").strip()[:400],
                }
            )
        return normalized

    def _extract_relationships_mock(
        self,
        *,
        book_title: str,
        characters: list[dict[str, str]],
        chapters: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        names = [str(item.get("name", "") or "").strip() for item in characters if str(item.get("name", "") or "").strip()]
        relationships: list[dict[str, str]] = []
        seen_pairs: set[tuple[str, str]] = set()
        type_keywords = [
            ("敌", "敌对"),
            ("仇", "敌对"),
            ("盟", "同盟"),
            ("合作", "合作"),
            ("朋友", "同伴"),
            ("同伴", "同伴"),
            ("师", "师徒"),
            ("父", "亲属"),
            ("母", "亲属"),
            ("兄", "亲属"),
            ("妹", "亲属"),
            ("爱", "情感"),
        ]
        for chapter in chapters:
            content = str(chapter.get("content", "") or "")
            title = str(chapter.get("title", "") or "章节")
            paragraphs = [part for part in re.split(r"\n\s*\n+|[。！？!?；;]", content) if part.strip()]
            for paragraph in paragraphs:
                mentioned = [name for name in names if name and name in paragraph]
                if len(mentioned) < 2:
                    continue
                relation_type = "关联"
                for keyword, label in type_keywords:
                    if keyword in paragraph:
                        relation_type = label
                        break
                for index, source in enumerate(mentioned):
                    for target in mentioned[index + 1:]:
                        pair = tuple(sorted((source, target)))
                        if pair in seen_pairs:
                            continue
                        seen_pairs.add(pair)
                        relationships.append(
                            {
                                "source_name": source,
                                "target_name": target,
                                "relationship_type": relation_type,
                                "description": f"本地分析：两人在《{title}》同段落出现。",
                            }
                        )
                        if len(relationships) >= 80:
                            return relationships
        return relationships

    def _extract_relationships_remote(
        self,
        *,
        book_title: str,
        characters: list[dict[str, str]],
        chapters: list[dict[str, Any]],
    ) -> dict[str, Any]:
        chapter_payload = []
        for item in chapters[:100]:
            chapter_payload.append(
                {
                    "title": str(item.get("title", "") or "")[:80],
                    "outline": str(item.get("outline", "") or "")[:800],
                    "content": str(item.get("content", "") or "")[:2400],
                }
            )
        prompt = (
            "请为小说书籍级人物星图抽取最终人际关系，只输出 JSON 对象，不要解释。\n"
            "JSON 字段：relationships 数组；每项包含 source_name, target_name, relationship_type, description。\n"
            "规则：\n"
            "- source_name 和 target_name 必须原样来自给定人物名单，不要发明新人物或使用代称。\n"
            "- 只保留全书最终状态下有明确互动、血缘、阵营、情感、师徒、敌对、合作或重要牵连的人物关系。\n"
            "- 不输出章节级变化，不输出同一对人物的重复关系。\n"
            "- relationship_type 使用 2-6 个汉字，例如 同盟、敌对、亲属、师徒、情感、合作、关联。\n"
            "- description 用一句话说明依据，控制在 80 字以内。\n\n"
            f"书名：{book_title or '未命名作品'}\n"
            f"具名人物名单：{json.dumps(characters[:60], ensure_ascii=False)}\n"
            f"章节内容：{json.dumps(chapter_payload, ensure_ascii=False)}"
        )
        result = self._post_chat_completion(
            messages=[
                {"role": "system", "content": "你是中文长篇小说的人物关系分析器，只返回指定 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.18,
        )
        raw_text = self._chat_completion_content(result, "人物关系分析")
        return self._extract_json_object_payload(raw_text)

    def _normalize_relationship_payload(
        self,
        payload: dict[str, Any],
        characters: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        if not isinstance(payload, dict):
            return []
        allowed: dict[str, str] = {}
        for item in characters:
            name = str(item.get("name", "") or "").strip()
            if name:
                allowed[self._relationship_name_key(name)] = name
        raw_relationships = payload.get("relationships", [])
        if not isinstance(raw_relationships, list):
            return []
        relationships: list[dict[str, str]] = []
        seen_pairs: set[tuple[str, str]] = set()
        for item in raw_relationships[:120]:
            if not isinstance(item, dict):
                continue
            source = allowed.get(self._relationship_name_key(item.get("source_name") or item.get("source") or ""))
            target = allowed.get(self._relationship_name_key(item.get("target_name") or item.get("target") or ""))
            if not source or not target or source == target:
                continue
            pair = tuple(sorted((source, target)))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            relationship_type = str(
                item.get("relationship_type") or item.get("type") or item.get("relation") or "关联"
            ).strip()
            description = str(item.get("description") or item.get("evidence") or "").strip()
            relationships.append(
                {
                    "source_name": source,
                    "target_name": target,
                    "relationship_type": (relationship_type or "关联")[:24],
                    "description": description[:160],
                }
            )
        return relationships

    @staticmethod
    def _relationship_name_key(value: Any) -> str:
        text = str(value or "").strip()
        text = re.sub(r"[（(].*?[）)]", "", text)
        text = re.sub(r"\s+", "", text)
        return text.casefold()

    def _analyze_remote(self, text: str) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "你是一个文档分类器。判断以下文档属于哪一类，只回复单个英文单词："
                    "body（小说正文/章节内容，哪怕含有目录、幕、章标题或分隔线）、"
                    "outline（只有结构/剧情梗概，没有连续正文）、"
                    "character（人物设定）、world（世界观设定）。"
                ),
            },
            {"role": "user", "content": text},
        ]
        result = self._post_chat_completion(messages, temperature=0.1)
        choices = result.get("choices", [])
        if choices:
            msg = choices[0].get("message", {}).get("content", "")
            result_clean = msg.strip().lower()
            for label in ("body", "outline", "character", "world"):
                if label in result_clean:
                    return label
        return "body"

    def _generate_by_mode(
        self,
        mode: str,
        book_title: str,
        chapter_title: str,
        outline: str,
        current_content: str = "",
        summary_text: str = "",
        selected_skills: list[dict[str, Any]] | None = None,
        sourcebook_context: str = "",
    ) -> str:
        selected_skills = selected_skills or []
        if self.api_key and self.model:
            try:
                return self._generate_remote(
                    mode=mode,
                    book_title=book_title,
                    chapter_title=chapter_title,
                    outline=outline,
                    current_content=current_content,
                    summary_text=summary_text,
                    selected_skills=selected_skills,
                    sourcebook_context=sourcebook_context,
                )
            except Exception as exc:
                self._remember_remote_error("生成", exc)

        return self._generate_mock(
            mode=mode,
            book_title=book_title,
            chapter_title=chapter_title,
            outline=outline,
            current_content=current_content,
            summary_text=summary_text,
            selected_skills=selected_skills,
            sourcebook_context=sourcebook_context,
        )

    def _generate_remote(
        self,
        mode: str,
        book_title: str,
        chapter_title: str,
        outline: str,
        current_content: str,
        summary_text: str,
        selected_skills: list[dict[str, Any]],
        sourcebook_context: str,
    ) -> str:
        prompt = self._build_remote_generation_prompt(
            mode=mode,
            book_title=book_title,
            chapter_title=chapter_title,
            outline=outline,
            current_content=current_content,
            summary_text=summary_text,
            skill_block=self._format_skill_block(selected_skills),
            sourcebook_context=sourcebook_context,
        )
        result = self._post_chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": "你是中文小说写作助手，帮助作者完成草稿生成、续写、润色和摘要提炼。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
        )
        return self._chat_completion_content(result, "章节生成")

    def _generate_remote_stream(
        self,
        mode: str,
        book_title: str,
        chapter_title: str,
        outline: str,
        current_content: str,
        summary_text: str,
        selected_skills: list[dict[str, Any]],
        sourcebook_context: str,
        cancel_event: Event | None = None,
    ) -> Iterator[str]:
        prompt = self._build_remote_generation_prompt(
            mode=mode,
            book_title=book_title,
            chapter_title=chapter_title,
            outline=outline,
            current_content=current_content,
            summary_text=summary_text,
            skill_block=self._format_skill_block(selected_skills),
            sourcebook_context=sourcebook_context,
        )
        for chunk in self._stream_chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": "你是中文小说写作助手，帮助作者完成草稿生成、续写、润色和摘要提炼。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            cancel_event=cancel_event,
        ):
            text = self._stream_delta_text(chunk)
            if text:
                yield text

    @staticmethod
    def _stream_delta_text(chunk: dict[str, Any]) -> str:
        choices = chunk.get("choices") if isinstance(chunk, dict) else None
        if not isinstance(choices, list) or not choices:
            return ""
        choice = choices[0]
        if not isinstance(choice, dict):
            return ""
        delta = choice.get("delta", {})
        if not isinstance(delta, dict):
            return ""
        content = delta.get("content", "")
        return content if isinstance(content, str) else ""

    def _summarize_remote(
        self,
        book_title: str,
        chapter_title: str,
        outline: str,
        content: str,
    ) -> str:
        prompt = (
            "请为下面的章节生成简洁中文摘要。\n"
            "要求：\n"
            "- 输出 3 到 5 句话\n"
            "- 提炼剧情推进、人物变化和关键悬念\n"
            "- 不使用列表，不重复大段正文\n\n"
            f"书名：{book_title or '未命名作品'}\n"
            f"章节：{chapter_title or '未命名章节'}\n"
            f"大纲：{outline or '暂无大纲'}\n"
            f"正文：\n{content[:6000]}"
        )
        result = self._post_chat_completion(
            messages=[
                {"role": "system", "content": "你擅长为中文小说章节提炼摘要。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
        )
        return self._chat_completion_content(result, "章节摘要")

    def _distill_remote(
        self,
        source_title: str,
        source_text: str,
    ) -> list[dict[str, str]]:
        prompt = (
            "请从下面的参考文本中提炼 3 到 5 个可复用的写作 Skills。\n"
            "注意：\n"
            "- 只提炼抽象技法，不要复写原句\n"
            "- 不要要求模仿具体作品\n"
            "- 只输出 JSON 数组\n"
            "- 每个对象包含 name, category, summary, instruction, use_cases, risk_note\n\n"
            f"参考标题：{source_title}\n"
            f"参考文本：\n{source_text[:6000]}"
        )
        result = self._post_chat_completion(
            messages=[
                {"role": "system", "content": "你擅长从文学文本中提炼抽象写作技巧。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
        )
        raw_text = self._chat_completion_content(result, "参考文本提炼")
        parsed = self._extract_json_payload(raw_text)

        skill_records: list[dict[str, str]] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            if not all(key in item for key in ("name", "category", "summary", "instruction")):
                continue
            skill_records.append(
                {
                    "name": str(item["name"]).strip(),
                    "category": str(item["category"]).strip(),
                    "summary": str(item["summary"]).strip(),
                    "instruction": str(item["instruction"]).strip(),
                    "use_cases": str(item.get("use_cases", "")).strip(),
                    "risk_note": str(item.get("risk_note", "")).strip(),
                }
            )
        return skill_records

    def _distill_project_remote(
        self,
        *,
        source_title: str,
        source_text: str,
        source_url: str,
        license_note: str,
        reusable_level: str,
    ) -> list[dict[str, str]]:
        prompt = (
            "请从下面的 GitHub/开源 AI 写作项目调研资料中提炼 4 到 6 个可复用 Skills。\n"
            "这些 Skills 要进入小说创作软件，不是复刻源项目。\n"
            "要求：\n"
            "- 只提炼抽象产品/写作工作流/提示词策略\n"
            "- 如果 license 未确认或 reusable_level 不是 compatible_code_allowed，必须明确禁止代码复用\n"
            "- 不要复制 README 原文，不要要求模仿具体项目\n"
            "- 只输出 JSON 数组\n"
            "- 每个对象包含 name, category, summary, instruction, use_cases, risk_note\n\n"
            f"项目：{source_title}\n"
            f"URL：{source_url or '未记录'}\n"
            f"License：{license_note or '待确认'}\n"
            f"Reuse level：{reusable_level or 'pattern_only'}\n"
            f"调研资料：\n{source_text[:7000]}"
        )
        result = self._post_chat_completion(
            messages=[
                {"role": "system", "content": "你擅长把 AI 写作产品调研提炼成可执行的抽象 Skills。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.35,
        )
        raw_text = self._chat_completion_content(result, "项目 Skills 提炼")
        parsed = self._extract_json_payload(raw_text)

        skill_records: list[dict[str, str]] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            if not all(key in item for key in ("name", "category", "summary", "instruction")):
                continue
            skill_records.append(
                {
                    "name": str(item["name"]).strip(),
                    "category": str(item["category"]).strip(),
                    "summary": str(item["summary"]).strip(),
                    "instruction": str(item["instruction"]).strip(),
                    "use_cases": str(item.get("use_cases", "")).strip(),
                    "risk_note": str(item.get("risk_note", "")).strip(),
                }
            )
        return skill_records

    def _post_chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float | None,
        extra_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": messages,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if isinstance(extra_body, dict):
            payload.update(extra_body)
        endpoint = self._chat_completion_endpoint()
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        req = request.Request(endpoint, data=data, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=120) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"HTTP {exc.code}: {body}") from exc

    @staticmethod
    def _chat_completion_content(result: dict[str, Any], purpose: str = "AI 请求") -> str:
        choices = result.get("choices") if isinstance(result, dict) else None
        if not isinstance(choices, list) or not choices:
            raise RuntimeError(f"{purpose}失败：AI 接口未返回 choices。")
        first = choices[0]
        if not isinstance(first, dict):
            raise RuntimeError(f"{purpose}失败：AI 接口返回格式无效。")
        message = first.get("message")
        if not isinstance(message, dict):
            raise RuntimeError(f"{purpose}失败：AI 接口未返回 message。")
        content = message.get("content")
        if content is None:
            raise RuntimeError(f"{purpose}失败：AI 接口未返回正文内容。")
        text = str(content).strip()
        if not text:
            raise RuntimeError(f"{purpose}失败：AI 接口返回内容为空。")
        return text

    def _stream_chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        cancel_event: Event | None = None,
    ) -> Iterator[dict[str, Any]]:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        endpoint = self._chat_completion_endpoint()
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        req = request.Request(endpoint, data=data, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=120) as response:
                for raw_line in response:
                    if cancel_event and cancel_event.is_set():
                        break
                    line = raw_line.decode("utf-8", errors="ignore").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    payload_text = line[5:].strip()
                    if payload_text == "[DONE]":
                        break
                    try:
                        yield json.loads(payload_text)
                    except json.JSONDecodeError:
                        continue
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"HTTP {exc.code}: {body}") from exc

    def _extract_json_payload(self, text: str) -> list[Any]:
        stripped = self._json_candidate_text(text, "[", "]")
        parsed = self._loads_json_payload(stripped)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict) and isinstance(parsed.get("skills"), list):
            return parsed["skills"]
        raise ValueError("Model did not return a JSON array.")

    def _extract_json_object_payload(self, text: str) -> dict[str, Any]:
        stripped = self._json_candidate_text(text, "{", "}")
        parsed = self._loads_json_payload(stripped)
        if isinstance(parsed, dict):
            return parsed
        raise ValueError("Model did not return a JSON object.")

    @staticmethod
    def _json_candidate_text(text: str, open_char: str, close_char: str) -> str:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", stripped)
            stripped = re.sub(r"\s*```$", "", stripped)
        start = stripped.find(open_char)
        end = stripped.rfind(close_char)
        if start != -1 and end != -1 and end > start:
            stripped = stripped[start : end + 1]
        return stripped

    @classmethod
    def _loads_json_payload(cls, text: str) -> Any:
        candidates = [text]
        repaired = cls._repair_json_like_text(text)
        if repaired != text:
            candidates.append(repaired)
        balanced = cls._balance_json_like_text(repaired)
        if balanced != repaired:
            candidates.append(balanced)
        last_error: Exception | None = None
        for candidate in candidates:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        return json.loads(text)

    @staticmethod
    def _repair_json_like_text(text: str) -> str:
        repaired = text.strip().lstrip("\ufeff")
        repaired = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", repaired)
        repaired = (
            repaired
            .replace("\u201c", '"')
            .replace("\u201d", '"')
            .replace("\u2018", "'")
            .replace("\u2019", "'")
        )
        repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
        key_pattern = r'"[^"\n\r]+":'
        repaired = re.sub(rf'([}}\]"])\s*\n\s*({key_pattern})', r"\1,\n\2", repaired)
        repaired = re.sub(rf'((?:true|false|null)|-?\d+(?:\.\d+)?)\s*\n\s*({key_pattern})', r"\1,\n\2", repaired)
        repaired = re.sub(r'([}\]"])\s*\n\s*([{\[])', r"\1,\n\2", repaired)
        repaired = re.sub(r'(")\s*\n\s*(")', r'\1,\n\2', repaired)
        return repaired

    @staticmethod
    def _balance_json_like_text(text: str) -> str:
        stack: list[str] = []
        in_string = False
        escaped = False
        for char in text:
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char in "{[":
                stack.append("}" if char == "{" else "]")
            elif char in "}]":
                if stack and stack[-1] == char:
                    stack.pop()
        if in_string:
            text += '"'
        if stack:
            text += "".join(reversed(stack))
        return text

    def _chunk_text(
        self,
        text: str,
        chunk_size: int = 80,
        cancel_event: Event | None = None,
    ) -> Iterator[str]:
        for index in range(0, len(text), chunk_size):
            if cancel_event and cancel_event.is_set():
                break
            yield text[index : index + chunk_size]

    def _chat_mock(self, messages: list[dict[str, str]]) -> str:
        user_messages = [item.get("content", "") for item in messages if item.get("role") == "user"]
        latest = user_messages[-1].strip() if user_messages else "请帮我检查当前章节。"
        return (
            "本地 Mock 对话：我已经收到你的问题。\n\n"
            f"你刚才说：{latest[:300]}\n\n"
            "如果要获得真实的多轮 AI 对话，请在 AI 设置中配置“AI 对话”用途。"
        )

    def _generate_mock(
        self,
        mode: str,
        book_title: str,
        chapter_title: str,
        outline: str,
        current_content: str,
        summary_text: str,
        selected_skills: list[dict[str, Any]],
        sourcebook_context: str,
    ) -> str:
        skill_names = [str(item.get("name", "")).strip() for item in selected_skills if str(item.get("name", "")).strip()]
        skill_hint = "、".join(skill_names[:2]) if skill_names else "场景铺陈"
        outline_hint = outline.strip() or "围绕当前冲突继续推进"
        summary_hint = summary_text.strip() or "前文已经建立了基础悬念"
        context_hint = self._compact_context_hint(sourcebook_context)

        if mode == "continue":
            anchor = current_content.strip()[-60:] if current_content.strip() else "空气里仍残留着尚未说明的异样"
            return "\n\n".join(
                [
                    f"{anchor}之后，新的细节开始显露出来。人物没有立刻做出激烈反应，而是先压住情绪，顺着现场留下的痕迹继续判断局势。",
                    f"这一段续写会沿着“{outline_hint}”往前推，同时保留 {skill_hint} 的节奏，并和 {context_hint} 保持一致。",
                    f"等角色真正意识到问题的严重性时，局面已经悄悄偏离了原来的预期，这也让《{book_title or '未命名作品'}》的《{chapter_title or '未命名章节'}》自然获得下一步推进空间。",
                ]
            )

        if mode == "polish":
            source = current_content.strip() or outline_hint
            trimmed = re.sub(r"\s+", " ", source)[:120]
            return "\n\n".join(
                [
                    f"{trimmed}。这段文字经过润色后，会更强调画面感与停顿，让人物动作、环境变化和情绪波动互相支撑，而不是平铺直叙地并列出现。",
                    f"在表达上，我会尽量保留原有信息，但把句式节奏调整得更顺，让关键细节落在更能被读者感知的位置，同时用 {skill_hint} 的方式增强段落层次，并避免偏离 {context_hint}。",
                    f"这样处理之后，这一段既不会脱离原本的剧情核心，也能和“{summary_hint}”形成更自然的呼应。",
                ]
            )

        return "\n\n".join(
            [
                f"《{book_title or '未命名作品'}》的《{chapter_title or '未命名章节'}》从“{outline_hint}”切入，先用环境和动作建立起稳定的画面，再把人物推到真正需要做决定的位置。",
                f"这一版草稿会吸收 {skill_hint} 的写法，并遵守 {context_hint}，让信息释放更均匀。人物不会直接把答案说出来，而是在观察、试探和短暂迟疑里，让读者先察觉到局势正在变化。",
                f"随着章节推进，前文提到的“{summary_hint}”会得到延展，新的线索被悄悄抛出，为后续续写、润色和摘要提炼保留足够空间。",
            ]
        )

    def _compact_context_hint(self, sourcebook_context: str) -> str:
        cleaned = re.sub(r"\s+", " ", sourcebook_context).strip()
        if not cleaned:
            return "当前书籍既有设定"
        return cleaned[:160]

    def _format_skill_block(self, selected_skills: list[dict[str, Any]]) -> str:
        if not selected_skills:
            return "Skills：无"

        lines = ["Skills："]
        for skill in selected_skills:
            instruction = skill.get("instruction_text") or skill.get("instruction") or ""
            lines.append(f"- {skill['name']}（{skill['category']}）：{instruction}")
        return "\n".join(lines)

    def _build_remote_generation_prompt(
        self,
        mode: str,
        book_title: str,
        chapter_title: str,
        outline: str,
        current_content: str,
        summary_text: str,
        skill_block: str,
        sourcebook_context: str,
    ) -> str:
        base = [
            f"书名：{book_title or '未命名作品'}",
            f"章节：{chapter_title or '未命名章节'}",
            f"大纲：{outline or '暂无大纲'}",
            f"已有摘要：{summary_text or '暂无摘要'}",
            "Sourcebook 上下文：",
            sourcebook_context.strip()[:5000] or "暂无 sourcebook 上下文",
            f"已有正文：{current_content or '暂无正文'}",
            skill_block,
            "",
        ]

        if mode == "continue":
            base.extend(
                [
                    "任务：请在现有正文基础上继续写一段新的内容。",
                    "要求：",
                    "- 输出 200 到 400 字",
                    "- 与前文自然衔接，不重复已经出现的内容",
                    "- 保持叙事视角、节奏和场景一致",
                ]
            )
        elif mode == "polish":
            base.extend(
                [
                    "任务：请在不改变剧情核心信息的前提下润色已有正文。",
                    "要求：",
                    "- 直接输出润色后的正文",
                    "- 优化语言节奏、画面感和连贯性",
                    "- 不要额外解释你的修改过程",
                ]
            )
        else:
            base.extend(
                [
                    "任务：请由多智能体流程生成一段新的章节草稿。",
                    "要求：",
                    "- 输出 300 到 500 字",
                    "- 保持自然叙事，不要解释思考过程",
                    "- 如果给出了 Skills，请把它们当作抽象约束，而不是模仿具体作品",
                ]
            )

        return "\n".join(base)
