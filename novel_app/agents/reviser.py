from __future__ import annotations

import json
from typing import Any, Callable

from novel_app.agents.prompts import REVISER_SYSTEM, REVISER_TEMPLATE
from novel_app.prompt_utils import prompt_value, render_prompt


class ReviserAgent:
    def __init__(self, post_chat: Callable[..., dict[str, Any]], prompt_overrides: dict[str, str] | None = None) -> None:
        self._post_chat = post_chat
        self._prompt_overrides = prompt_overrides or {}

    def revise(self, state: Any) -> None:
        content = state.draft or state.current_content
        if not state.audit_findings:
            state.revised_content = content
            state.revised_outline = state.outline
            state.risk_notes = ""
            state.template_comparison = ""
            state.log("无审计问题，跳过修订")
            return

        findings_text = "\n".join(
            f"[{f['severity']}] {f.get('agent', '')}/{f.get('category', '')}：{f['issue'][:200]} → {f['suggestion'][:200]}"
            for f in state.audit_findings[:15]
        )
        prompt = render_prompt(
            prompt_value(self._prompt_overrides, "agent.reviser.template", REVISER_TEMPLATE),
            {
                "book_title": state.book_title,
                "chapter_title": state.chapter_title,
                "outline": state.outline,
                "content": content[:12000],
                "findings": findings_text,
                "template_content": state.template_content[:2000],
            },
        )
        result = self._post_chat(
            messages=[
                {"role": "system", "content": prompt_value(self._prompt_overrides, "agent.reviser.system", REVISER_SYSTEM)},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
        )
        raw = result["choices"][0]["message"]["content"].strip()
        try:
            payload = self._extract_json(raw)
        except Exception as e:
            state.log(f"Reviser JSON 解析失败: {e}")
            state.revised_content = content
            state.revised_outline = state.outline
            state.risk_notes = ""
            state.template_comparison = ""
            return
        revised = str(payload.get("revised_content", "") or "").strip()
        if not revised:
            state.revised_content = content
            state.log("Reviser 返回空内容，保留原稿")
        else:
            state.revised_content = revised
        state.revised_outline = str(payload.get("revised_outline", "") or "").strip() or state.outline
        state.risk_notes = str(payload.get("risk_notes", "") or "").strip()
        state.template_comparison = str(payload.get("template_comparison", "") or "").strip()
        state.log(f"Reviser 完成修订，产出 {len(state.revised_content)} 字")

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        import re
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", stripped)
            stripped = re.sub(r"\s*```$", "", stripped)
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start != -1 and end != -1 and end > start:
            stripped = stripped[start:end + 1]
        return json.loads(stripped)
