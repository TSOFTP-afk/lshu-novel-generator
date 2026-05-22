from __future__ import annotations

from typing import Any, Callable

from novel_app.agents.prompts import WRITER_SYSTEM, WRITER_TEMPLATE
from novel_app.prompt_utils import prompt_value, render_prompt


class WriterAgent:
    def __init__(self, post_chat: Callable[..., dict[str, Any]], prompt_overrides: dict[str, str] | None = None) -> None:
        self._post_chat = post_chat
        self._prompt_overrides = prompt_overrides or {}

    def write(self, state: Any) -> None:
        skills = state.selected_skills or []
        skill_text = "\n".join(
            f"- {s.get('name', '')}：{s.get('instruction_text', s.get('instruction', ''))}"
            for s in skills[:8]
        ) if skills else "无"

        prompt = WRITER_TEMPLATE.format(
            book_title=state.book_title,
            chapter_title=state.chapter_title,
            outline=state.outline,
            plan=state.plan,
            current_content=state.current_content[:5000] or "（全新章节）",
            skills=skill_text,
            truth_file=state.truth_file[:6000],
            sourcebook_context=state.sourcebook_context[:3000],
            template_content=state.template_content[:2000],
            style_voices_block=state.style_voices_block[:2000],
        )
        prompt = render_prompt(
            prompt_value(self._prompt_overrides, "agent.writer.template", WRITER_TEMPLATE),
            {
                "book_title": state.book_title,
                "chapter_title": state.chapter_title,
                "outline": state.outline,
                "plan": state.plan,
                "current_content": state.current_content[:5000],
                "skills": skill_text,
                "truth_file": state.truth_file[:6000],
                "sourcebook_context": state.sourcebook_context[:3000],
                "template_content": state.template_content[:2000],
                "style_voices_block": state.style_voices_block[:2000],
            },
        )
        try:
            result = self._post_chat(
                messages=[
                    {"role": "system", "content": prompt_value(self._prompt_overrides, "agent.writer.system", WRITER_SYSTEM)},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
            )
            raw = result["choices"][0]["message"]["content"].strip()
            state.draft = raw
        except (KeyError, IndexError) as e:
            state.log(f"Writer JSON 解析失败: {e}")
            state.draft = (
                f"【AI 写作异常】{state.chapter_title}\n\n"
                "写作模块返回格式异常，请检查 AI 配置或使用本地 Mock 生成。"
            )
        state.log(f"Writer 生成正文 {len(state.draft)} 字")
