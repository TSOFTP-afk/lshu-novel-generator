from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ParsedChapter:
    title: str
    content: str
    outline: str
    volume_title: str | None = None


@dataclass(frozen=True)
class ParsedBook:
    title: str
    outline: str
    chapters: list[ParsedChapter]


_CN_NUM = r"\d零〇一二两三四五六七八九十百千万"
_VOLUME_RE = re.compile(
    rf"^\s*(第\s*[{_CN_NUM}]+\s*[卷部篇集]|卷\s*[{_CN_NUM}]+|Volume\s+\d+|Book\s+\d+).*$",
    re.IGNORECASE,
)
_STRONG_CHAPTER_RE = re.compile(
    rf"^\s*(第\s*[{_CN_NUM}]+\s*[章节回]|章节\s*\d+|Chapter\s+\d+|序章|楔子|尾声|番外)(?:\s+.*|[：:·、.．\-—_].*)?$",
    re.IGNORECASE,
)
_ACT_RE = re.compile(
    rf"^\s*第\s*[{_CN_NUM}]+\s*幕(?:\s+.*|[：:·、.．\-—_].*)?$",
    re.IGNORECASE,
)
_PIPE_SECTION_RE = re.compile(
    rf"^\s*[|｜]\s*[{_CN_NUM}]+\s*[|｜]\s*\S+.*$",
    re.IGNORECASE,
)
_NUMBERED_SECTION_RE = re.compile(
    r"^\s*\d+\s*[.．、]\s*\S+.*$",
    re.IGNORECASE,
)
_SENTENCE_RE = re.compile(r"(?<=[。！？!?；;])\s*")


def parse_long_text(
    book_title: str,
    raw_text: str,
    chapter_structure: list[dict[str, Any]] | None = None,
    use_local_headings: bool = True,
) -> ParsedBook:
    text = _normalize_text(raw_text)
    if not text:
        return ParsedBook(title=book_title.strip() or "未命名导入作品", outline="", chapters=[])

    chapters: list[ParsedChapter]
    explicit_chapter_count = 0
    if chapter_structure:
        chapters = _parse_by_detected_structure(text, chapter_structure)
        explicit_chapter_count = len(chapters)
        if not chapters and not use_local_headings:
            chapters = [ParsedChapter(title="第1章", content=text.strip(), outline="", volume_title=None)]
    elif use_local_headings:
        chapters, explicit_chapter_count = _parse_by_headings(text)
    else:
        chapters = [ParsedChapter(title="第1章", content=text.strip(), outline="", volume_title=None)]
    if explicit_chapter_count == 0:
        chapters = _chunk_implicit_chapters(chapters)

    normalized_chapters = [
        ParsedChapter(
            title=chapter.title,
            content=chapter.content,
            outline=_extract_chapter_outline(chapter.title, chapter.content),
            volume_title=chapter.volume_title,
        )
        for chapter in chapters
        if chapter.content.strip()
    ]
    return ParsedBook(
        title=book_title.strip() or "未命名导入作品",
        outline=_extract_book_outline(book_title, normalized_chapters),
        chapters=normalized_chapters,
    )


def _parse_by_detected_structure(text: str, chapter_structure: list[dict[str, Any]]) -> list[ParsedChapter]:
    markers = _normalize_structure_markers(chapter_structure)
    if not any(marker["kind"] == "chapter" for marker in markers):
        return []

    markers_by_line: dict[int, list[dict[str, Any]]] = {}
    for marker in markers:
        markers_by_line.setdefault(int(marker["line_number"]), []).append(marker)

    chapters: list[ParsedChapter] = []
    current_volume: str | None = None
    current_title: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer, current_title
        content = "\n".join(buffer).strip()
        if current_title and content:
            chapters.append(ParsedChapter(title=current_title, content=content, outline="", volume_title=current_volume))
        buffer = []

    for line_number, raw_line in enumerate(text.split("\n"), start=1):
        line_markers = markers_by_line.get(line_number, [])
        volume_markers = [item for item in line_markers if item["kind"] == "volume"]
        chapter_markers = [item for item in line_markers if item["kind"] == "chapter"]
        if volume_markers:
            flush()
            current_volume = str(volume_markers[-1]["title"])
            current_title = None
            continue
        if chapter_markers:
            flush()
            current_title = str(chapter_markers[-1]["title"])
            continue
        if current_title:
            buffer.append(raw_line)
    flush()
    return chapters


def _normalize_structure_markers(chapter_structure: list[dict[str, Any]]) -> list[dict[str, Any]]:
    markers: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for item in chapter_structure:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind", "") or "").strip().lower()
        if kind not in {"volume", "chapter"}:
            continue
        try:
            line_number = int(item.get("line_number", item.get("line", 0)) or 0)
        except (TypeError, ValueError):
            continue
        title = str(item.get("title", "") or "").strip()
        if line_number <= 0 or not title:
            continue
        key = (kind, line_number)
        if key in seen:
            continue
        seen.add(key)
        markers.append({"kind": kind, "line_number": line_number, "title": title})
    markers.sort(key=lambda item: (int(item["line_number"]), 0 if item["kind"] == "volume" else 1))
    return markers


def _normalize_text(raw_text: str) -> str:
    text = raw_text.replace("\ufeff", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def _parse_by_headings(text: str) -> tuple[list[ParsedChapter], int]:
    chapters: list[ParsedChapter] = []
    current_volume: str | None = None
    current_title: str | None = None
    buffer: list[str] = []
    explicit_chapter_count = 0
    strong_count, act_count, pipe_section_count, numbered_section_count = _count_heading_candidates(text)
    allow_pipe_sections = pipe_section_count >= 2
    allow_numbered_sections = strong_count < 2 and numbered_section_count >= 2
    use_acts_as_volumes = act_count >= 2 and (allow_pipe_sections or strong_count >= 2 or numbered_section_count >= 2)

    def flush() -> None:
        nonlocal buffer, current_title
        content = "\n".join(buffer).strip()
        if content:
            title = current_title or f"第{len(chapters) + 1}章"
            chapters.append(ParsedChapter(title=title, content=content, outline="", volume_title=current_volume))
        buffer = []

    for raw_line in text.split("\n"):
        line = _clean_heading_line(raw_line)
        if not chapters and not buffer and _is_front_matter_noise(line):
            current_title = None
            continue
        if line and len(line) <= 80 and _VOLUME_RE.match(line):
            flush()
            current_volume = line
            current_title = None
            continue
        if line and len(line) <= 100 and use_acts_as_volumes and _ACT_RE.match(line):
            flush()
            current_volume = line
            current_title = None
            continue
        if line and len(line) <= 100 and _is_chapter_heading(
            line,
            allow_pipe_sections,
            allow_numbered_sections,
            use_acts_as_volumes,
        ):
            flush()
            current_title = line
            explicit_chapter_count += 1
            continue
        buffer.append(raw_line)
    flush()

    if not chapters and text.strip():
        chapters.append(ParsedChapter(title="第1章", content=text.strip(), outline="", volume_title=None))
    return chapters, explicit_chapter_count


def _clean_heading_line(raw_line: str) -> str:
    line = raw_line.strip().strip("\ufeff")
    line = re.sub(r"^\s*[#>*\-=—_＿~～·•\s]+", "", line)
    line = re.sub(r"[\-=—_＿~～·•\s]+$", "", line)
    return line.strip()


def _is_front_matter_noise(line: str) -> bool:
    compact = re.sub(r"\s+", "", line or "")
    return compact in {"目录", "作品目录", "章节目录", "正文", "正文开始", "内容简介"}


def _is_chapter_heading(
    line: str,
    allow_pipe_sections: bool,
    allow_numbered_sections: bool,
    use_acts_as_volumes: bool,
) -> bool:
    if not use_acts_as_volumes and _ACT_RE.match(line):
        return True
    if _STRONG_CHAPTER_RE.match(line):
        return True
    if allow_pipe_sections and _PIPE_SECTION_RE.match(line):
        return True
    return allow_numbered_sections and bool(_NUMBERED_SECTION_RE.match(line))


def _count_heading_candidates(text: str) -> tuple[int, int, int, int]:
    strong_count = 0
    act_count = 0
    pipe_section_count = 0
    numbered_section_count = 0
    for raw_line in text.split("\n"):
        line = _clean_heading_line(raw_line)
        if not line or len(line) > 100 or _VOLUME_RE.match(line):
            continue
        if _ACT_RE.match(line):
            act_count += 1
        elif _STRONG_CHAPTER_RE.match(line):
            strong_count += 1
        elif _PIPE_SECTION_RE.match(line):
            pipe_section_count += 1
        elif _NUMBERED_SECTION_RE.match(line):
            numbered_section_count += 1
    return strong_count, act_count, pipe_section_count, numbered_section_count


def _chunk_implicit_chapters(chapters: list[ParsedChapter]) -> list[ParsedChapter]:
    chunked: list[ParsedChapter] = []
    for chapter in chapters:
        chunks = _split_into_chunks(chapter.content)
        if len(chunks) == 1:
            title = chapter.title if chapter.title != "第1章" or chapter.volume_title is None else f"{chapter.volume_title} 第1章"
            chunked.append(ParsedChapter(title=title, content=chunks[0], outline="", volume_title=chapter.volume_title))
            continue
        for index, chunk in enumerate(chunks, start=1):
            title = f"第{len(chunked) + 1}章"
            if chapter.volume_title:
                title = f"{chapter.volume_title} 第{index}章"
            chunked.append(ParsedChapter(title=title, content=chunk, outline="", volume_title=chapter.volume_title))
    return chunked


def _split_into_chunks(text: str, target_size: int = 4500, hard_size: int = 6800) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", text) if part.strip()]
    if not paragraphs:
        paragraphs = [text.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_size = 0
    for paragraph in paragraphs:
        if len(paragraph) > hard_size:
            if current:
                chunks.append("\n\n".join(current).strip())
                current = []
                current_size = 0
            chunks.extend(_split_large_paragraph(paragraph, target_size))
            continue
        if current and current_size + len(paragraph) > target_size:
            chunks.append("\n\n".join(current).strip())
            current = [paragraph]
            current_size = len(paragraph)
        else:
            current.append(paragraph)
            current_size += len(paragraph)
    if current:
        chunks.append("\n\n".join(current).strip())
    return [chunk for chunk in chunks if chunk.strip()]


def _split_large_paragraph(paragraph: str, target_size: int) -> list[str]:
    sentences = [item.strip() for item in _SENTENCE_RE.split(paragraph) if item.strip()]
    if len(sentences) <= 1:
        return [paragraph[index : index + target_size].strip() for index in range(0, len(paragraph), target_size)]
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for sentence in sentences:
        if current and size + len(sentence) > target_size:
            chunks.append("".join(current).strip())
            current = [sentence]
            size = len(sentence)
        else:
            current.append(sentence)
            size += len(sentence)
    if current:
        chunks.append("".join(current).strip())
    return chunks


def _extract_chapter_outline(title: str, content: str) -> str:
    sentences = _pick_sentences(content, limit=4)
    if not sentences:
        sentences = [content.strip()[:160]]
    lines = [f"自动提炼大纲：{title}", f"字数：{len(content.strip())}"]
    for sentence in sentences:
        lines.append(f"- {sentence[:180]}")
    return "\n".join(lines)


def _extract_book_outline(book_title: str, chapters: list[ParsedChapter]) -> str:
    volume_titles = []
    seen = set()
    for chapter in chapters:
        if chapter.volume_title and chapter.volume_title not in seen:
            volume_titles.append(chapter.volume_title)
            seen.add(chapter.volume_title)
    total_chars = sum(len(chapter.content.strip()) for chapter in chapters)
    lines = [
        f"自动导入总纲：{book_title.strip() or '未命名导入作品'}",
        f"规模：{len(volume_titles)} 卷 / {len(chapters)} 章 / {total_chars} 字",
    ]
    if volume_titles:
        lines.append("卷结构：")
        for title in volume_titles[:20]:
            lines.append(f"- {title}")
    lines.append("章节结构：")
    for chapter in chapters[:40]:
        prefix = f"{chapter.volume_title} / " if chapter.volume_title else ""
        lines.append(f"- {prefix}{chapter.title}")
    if len(chapters) > 40:
        lines.append(f"- ... 另有 {len(chapters) - 40} 章")
    return "\n".join(lines)


def _pick_sentences(content: str, limit: int) -> list[str]:
    compact = re.sub(r"\s+", " ", content).strip()
    sentences = [item.strip() for item in _SENTENCE_RE.split(compact) if len(item.strip()) >= 8]
    picked: list[str] = []
    if sentences:
        picked.append(sentences[0])
    if len(sentences) >= 3:
        picked.append(sentences[len(sentences) // 2])
    if len(sentences) >= 2:
        picked.append(sentences[-1])
    for sentence in sentences:
        if len(picked) >= limit:
            break
        if sentence not in picked:
            picked.append(sentence)
    return picked[:limit]
