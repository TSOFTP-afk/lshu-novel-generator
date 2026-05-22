from __future__ import annotations

import json
from typing import Any, Callable

from novel_app.agents.prompts import PLANNER_SYSTEM, PLANNER_TEMPLATE
from novel_app.prompt_utils import prompt_value, render_prompt


class PlannerAgent:
    def __init__(self, post_chat: Callable[..., dict[str, Any]], prompt_overrides: dict[str, str] | None = None) -> None:
        self._post_chat = post_chat
        self._prompt_overrides = prompt_overrides or {}

    def plan(self, state: Any) -> None:
        prompt = render_prompt(
            prompt_value(self._prompt_overrides, "agent.planner.template", PLANNER_TEMPLATE),
            {
                "book_title": state.book_title,
                "chapter_title": state.chapter_title,
                "outline": state.outline,
                "truth_file": state.truth_file[:6000],
                "sourcebook_context": state.sourcebook_context[:3000],
            },
        )
        result = self._post_chat(
            messages=[
                {"role": "system", "content": prompt_value(self._prompt_overrides, "agent.planner.system", PLANNER_SYSTEM)},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        raw = result["choices"][0]["message"]["content"].strip()
        try:
            payload = self._extract_json(raw)
        except Exception as e:
            state.log(f"Planner JSON 解析失败: {e}")
            state.plan = f"围绕「{state.outline[:200]}」按场景推进"
            return
        scenes = payload.get("scene_plan", [])
        if not isinstance(scenes, list):
            scenes = []
        plan_lines = []
        for s in scenes[:5]:
            if not isinstance(s, dict):
                continue
            parts = [
                f"场景{s.get('scene_number', '?')}：{s.get('scene_goal', '未指定')}",
                f"地点：{s.get('location', '未指定')}",
            ]
            beats = s.get("key_beats", [])
            if isinstance(beats, list):
                parts.append("关键节拍：" + "；".join(str(b) for b in beats[:3]))
            plan_lines.append(" | ".join(parts))
        state.plan = "\n".join(plan_lines) if plan_lines else f"围绕「{state.outline[:200]}」按场景推进"
        state.log(f"Planner 生成 {len(scenes)} 个场景计划")

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
