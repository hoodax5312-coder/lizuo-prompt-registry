from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from markdown_it import MarkdownIt
from markdown_it.token import Token

from .models import Source, absolute_url, deduplicate, inline, make_prompt, unique


MARKDOWN = MarkdownIt("commonmark", {"html": True}).enable("table")


def parse_source(source: Source, payload: bytes) -> list[dict[str, Any]]:
    parser = PARSERS.get(source.adapter)
    if not parser:
        raise ValueError(f"Unknown adapter {source.adapter!r} for {source.id}")
    items = parser(source, payload)
    if len(items) < source.minimum_items:
        raise ValueError(
            f"{source.id} produced {len(items)} items; expected at least {source.minimum_items}"
        )
    return items


def parse_banana_json(source: Source, payload: bytes) -> list[dict[str, Any]]:
    data = load_json_array(source, payload)
    return deduplicate(
        make_prompt(
            source,
            raw_id=f"{item.get('created', '')}|{item.get('title', '')}",
            title=item.get("title"),
            prompt=item.get("prompt"),
            cover_url=item.get("preview"),
            reference_image_urls=array(item.get("reference_image_urls")),
            tags=(item.get("category"), item.get("sub_category"), item.get("author")),
            author=item.get("author"),
            created_at=item.get("created"),
            image_mode=item.get("mode"),
        )
        for item in data
    )


def parse_davidwu_json(source: Source, payload: bytes) -> list[dict[str, Any]]:
    data = load_json_array(source, payload)
    result = []
    for index, item in enumerate(data, 1):
        image = item.get("image")
        tags = [item.get("category_cn"), item.get("category"), item.get("author"), item.get("source")]
        if item.get("needs_ref"):
            tags.append("需要参考图")
        result.append(
            make_prompt(
                source,
                raw_id=item.get("id") or index,
                title=item.get("title_cn") or item.get("title_en"),
                prompt=item.get("prompt"),
                description=item.get("note"),
                cover_url=image,
                reference_image_urls=[image] if image else [],
                tags=tags,
                author=item.get("author"),
                image_model="gpt-image-2",
            )
        )
    return deduplicate(result)


def parse_freestylefly_json(source: Source, payload: bytes) -> list[dict[str, Any]]:
    data = json.loads(payload.decode("utf-8-sig"))
    cases = data.get("cases") if isinstance(data, dict) else None
    if not isinstance(cases, list) or not all(isinstance(item, dict) for item in cases):
        raise ValueError(f"{source.id} must contain a cases array of objects")

    result = []
    for item in cases:
        image = inline(item.get("image")).lstrip("/")
        tags = [
            source.model,
            item.get("category"),
            *array(item.get("styles")),
            *array(item.get("scenes")),
        ]
        if item.get("featured") is True:
            tags.append("featured")
        result.append(
            make_prompt(
                source,
                raw_id=item.get("id"),
                title=item.get("title"),
                prompt=item.get("prompt"),
                cover_url=image,
                reference_image_urls=[image] if image else [],
                tags=tags,
                author=item.get("sourceLabel"),
                source_url=item.get("sourceUrl") or item.get("githubUrl"),
            )
        )
    return deduplicate(result)


def parse_awesome_gpt_image(source: Source, payload: bytes) -> list[dict[str, Any]]:
    result = []
    for title, category, tokens in markdown_sections(decode(payload)):
        prompt = prompt_fence(tokens)
        if not prompt:
            continue
        images = extract_images(source, tokens)
        author, item_url = labeled_link(tokens, "来源")
        result.append(
            make_prompt(
                source,
                title=title,
                prompt=prompt,
                description=first_paragraph(tokens, exclude=("提示词", "来源")),
                cover_url=images[0] if images else "",
                reference_image_urls=images,
                tags=[clean_category(category), author],
                author=author,
                source_url=item_url,
                image_model="gpt-image-2",
            )
        )
    return deduplicate(result)


def parse_awesome_gpt4o(source: Source, payload: bytes) -> list[dict[str, Any]]:
    result = []
    for title, _category, tokens in markdown_sections(decode(payload)):
        prompt = labeled_code(tokens, "提示词文本")
        if not prompt:
            continue
        images = extract_images(source, tokens)
        author, item_url = labeled_link(tokens, "作者")
        result.append(
            make_prompt(
                source,
                title=title,
                prompt=prompt,
                description=first_paragraph(tokens, exclude=("模型", "提示词文本", "示例图片", "作者")),
                cover_url=images[0] if images else "",
                reference_image_urls=images,
                tags=["gpt4o", author],
                author=author,
                source_url=item_url,
                image_model="gpt4o",
            )
        )
    return deduplicate(result)


def parse_youmind(source: Source, payload: bytes) -> list[dict[str, Any]]:
    result = []
    for raw_title, _category, tokens in markdown_sections(decode(payload)):
        match = re.match(r"No\.\s*(\d+)\s*[:：]\s*(.+)", raw_title, re.I)
        if not match:
            continue
        item_number, title = match.groups()
        prompt = prompt_fence(tokens)
        if not prompt:
            continue
        images = extract_images(source, tokens)
        category = title.split(" - ", 1)[0] if " - " in title else ""
        author, _author_url = labeled_link(tokens, "作者")
        _source_name, item_url = labeled_link(tokens, "来源")
        result.append(
            make_prompt(
                source,
                raw_id=f"{item_number}\n{title}\n{prompt}",
                title=title,
                prompt=prompt,
                description=paragraph_after_heading(tokens, "描述"),
                cover_url=images[0] if images else "",
                reference_image_urls=images,
                tags=[source.model, category, author],
                author=author,
                source_url=item_url,
                created_at=published_date(tokens),
                image_model=source.model,
            )
        )
    return deduplicate(result)


def parse_seedance(source: Source, payload: bytes) -> list[dict[str, Any]]:
    """Parse YouMind's Seedance README, including the unnumbered full catalog."""
    result = []
    for raw_title, category, tokens in markdown_sections(decode(payload)):
        if "更多提示词未在此显示" in raw_title:
            continue
        prompt = prompt_fence(tokens)
        if not prompt:
            continue
        images = extract_images(source, tokens)
        author, _author_url = labeled_link(tokens, "作者")
        _source_name, item_url = labeled_link(tokens, "来源")
        result.append(
            make_prompt(
                source,
                raw_id=f"{raw_title}\n{prompt}",
                title=raw_title,
                prompt=prompt,
                description=first_paragraph(tokens, exclude=("提示词", "作者", "来源", "发布时间")),
                cover_url=images[0] if images else "",
                reference_image_urls=images,
                tags=[source.model, clean_category(category), author],
                author=author,
                source_url=item_url,
                created_at=published_date_flexible(tokens),
                image_model=source.model,
            )
        )
    return deduplicate(result)


def parse_zerolu_nanobanana(source: Source, payload: bytes) -> list[dict[str, Any]]:
    """Parse ZeroLu's English README: "### 1.1. Title", **Prompt:** fence, *Source: [@x](url)*."""
    result = []
    for raw_title, category, tokens in markdown_sections(decode(payload)):
        match = re.match(r"\d+(?:\.\d+)*\.?\s+(.+)", raw_title)
        if not match:
            continue
        prompt = prompt_fence(tokens, "Prompt")
        if not prompt:
            continue
        images = extract_images(source, tokens)
        author, item_url = labeled_link(tokens, "Source")
        # The caption shares a paragraph with an inline <img>, which first_paragraph would skip.
        description = next(
            (
                text
                for token in tokens
                if token.type == "inline"
                and (text := token_text(token))
                and "Prompt" not in text
                and "Source" not in text
            ),
            "",
        )
        result.append(
            make_prompt(
                source,
                title=match.group(1),
                prompt=prompt,
                description=description,
                cover_url=images[0] if images else "",
                reference_image_urls=images,
                tags=[source.model, re.sub(r"^[\d.\s]+", "", clean_category(category)), author],
                author=author,
                source_url=item_url,
                image_model=source.model,
            )
        )
    return deduplicate(result)


def parse_picotrex(source: Source, payload: bytes) -> list[dict[str, Any]]:
    """Parse PicoTrex's README: "### 例 N: [标题](链接)（by [@作者](链接)）" and a **提示词:** fence."""
    result = []
    for raw_title, _category, tokens in markdown_sections(decode(payload)):
        match = re.match(r"例\s*(\d+)\s*[:：]\s*(.+)", raw_title)
        if not match:
            continue
        prompt = prompt_fence(tokens)
        if not prompt:
            continue
        item_number, heading = match.groups()
        by = re.search(r"[（(]\s*by\s+([^）)]+)[）)]\s*$", heading, re.I)
        title = heading[: by.start()].strip() if by else heading
        author = inline(by.group(1)) if by else ""
        images = extract_images(source, tokens)
        result.append(
            make_prompt(
                source,
                raw_id=f"{item_number}\n{title}\n{prompt}",
                title=title,
                prompt=prompt,
                cover_url=images[0] if images else "",
                reference_image_urls=images,
                tags=[source.model, author],
                author=author,
                image_model=source.model,
            )
        )
    return deduplicate(result)


# Parameters only Midjourney accepts. A bare --ar is excluded because other models' prompts borrow it.
MIDJOURNEY_PARAMETER = re.compile(
    r"(?<![\w-])--(?:v|version|niji|sref|cref|oref|style|stylize|s|chaos|c|weird|w|personalize|p"
    r"|iw|sw|cw|ow|q|quality|no|tile|raw)\b",
    re.I,
)


def youmind_skill_files(source: Source, payload: bytes) -> list[tuple[str, str]]:
    """List (category title, file URL) pairs from the skill's references/manifest.json."""
    manifest = json.loads(decode(payload))
    categories = manifest.get("categories") if isinstance(manifest, dict) else None
    if not isinstance(categories, list) or not categories:
        raise ValueError(f"{source.id} manifest must contain a categories array")
    result = []
    for category in categories:
        url = absolute_url(source.url, category.get("file")) if isinstance(category, dict) else ""
        if not url:
            raise ValueError(f"{source.id} manifest lists a category without a file")
        result.append((inline(category.get("title")), url))
    return result


def parse_youmind_skill_midjourney(source: Source, payload: bytes) -> list[dict[str, Any]]:
    """Keep YouMind skill prompts written in Midjourney syntax; the upstream data has no model field."""
    data = json.loads(decode(payload))
    categories = data.get("categories") if isinstance(data, dict) else None
    if not isinstance(categories, list):
        raise ValueError(f"{source.id} bundle must contain a categories array")
    result = []
    for category in categories:
        items = category.get("items") if isinstance(category, dict) else None
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            raise ValueError(f"{source.id} category files must be JSON arrays of objects")
        for item in items:
            prompt = item.get("content")
            if not MIDJOURNEY_PARAMETER.search(str(prompt or "")):
                continue
            images = array(item.get("sourceMedia"))
            tags = [source.model, category.get("title")]
            if item.get("needReferenceImages") is True:
                tags.append("需要参考图")
            result.append(
                make_prompt(
                    source,
                    raw_id=item.get("id"),
                    title=item.get("title"),
                    prompt=prompt,
                    description=item.get("description"),
                    cover_url=images[0] if images else "",
                    reference_image_urls=images,
                    tags=tags,
                    image_model=source.model,
                )
            )
    return deduplicate(result)


def load_json_array(source: Source, payload: bytes) -> list[dict[str, Any]]:
    data = json.loads(payload.decode("utf-8-sig"))
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise ValueError(f"{source.id} must return a JSON array of objects")
    return data


def decode(payload: bytes) -> str:
    return payload.decode("utf-8-sig")


def array(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


def markdown_sections(text: str) -> Iterable[tuple[str, str, list[Token]]]:
    tokens = MARKDOWN.parse(text)
    category = ""
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.type == "heading_open" and token.tag == "h2":
            category = heading_text(tokens, index)
            index += 3
            continue
        if token.type != "heading_open" or token.tag != "h3":
            index += 1
            continue
        title = heading_text(tokens, index)
        end = index + 3
        while end < len(tokens):
            candidate = tokens[end]
            if candidate.type == "heading_open" and candidate.tag in {"h2", "h3"}:
                break
            end += 1
        yield title, category, tokens[index + 3 : end]
        index = end


def heading_text(tokens: list[Token], index: int) -> str:
    if index + 1 >= len(tokens) or tokens[index + 1].type != "inline":
        return ""
    return token_text(tokens[index + 1])


def token_text(token: Token) -> str:
    if not token.children:
        return inline(token.content)
    parts = []
    for child in token.children:
        if child.type in {"text", "code_inline", "image"}:
            parts.append(child.content)
        elif child.type in {"softbreak", "hardbreak"}:
            parts.append(" ")
    return inline("".join(parts))


def prompt_fence(tokens: list[Token], marker: str = "提示词") -> str:
    marker_seen = False
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.type == "heading_open" and token.tag == "h4":
            marker_seen = marker in heading_text(tokens, index)
            index += 3
            continue
        if token.type == "inline" and marker in token_text(token):
            marker_seen = True
        elif marker_seen and token.type == "fence":
            return token.content.strip()
        index += 1
    return ""


def labeled_code(tokens: list[Token], label: str) -> str:
    for index, token in enumerate(tokens):
        if token.type != "inline" or label not in token_text(token):
            continue
        for child in token.children or []:
            if child.type == "code_inline" and child.content.strip():
                return child.content.strip()
        opening = token.content.find("`", token.content.find(label) + len(label))
        if opening < 0:
            continue
        parts = [token.content[opening + 1 :]]
        for candidate in tokens[index + 1 :]:
            if candidate.type != "inline":
                continue
            closing = candidate.content.find("`")
            if closing >= 0:
                parts.append(candidate.content[:closing])
                return "\n\n".join(parts).strip()
            parts.append(candidate.content)
    return ""


def token_links(token: Token) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    href = ""
    label: list[str] = []
    for child in token.children or []:
        if child.type == "link_open":
            href = child.attrGet("href") or ""
            label = []
        elif child.type == "link_close" and href:
            result.append((inline("".join(label)), href))
            href = ""
        elif href and child.type in {"text", "code_inline", "image"}:
            label.append(child.content)
    return result


def labeled_link(tokens: list[Token], label: str) -> tuple[str, str]:
    for token in tokens:
        if token.type not in {"inline", "html_block"}:
            continue
        value = token_text(token) if token.type == "inline" else token.content
        if label not in value:
            continue
        if token.type == "html_block":
            match = re.search(rf"{re.escape(label)}.*?\[([^\]]+)\]\(([^)]+)\)", token.content, re.S)
            if match:
                return inline(match.group(1)), match.group(2)
            continue
        seen_label = False
        href = ""
        text_parts: list[str] = []
        for child in token.children or []:
            if child.type == "text":
                text_parts.append(child.content)
                if label in child.content:
                    seen_label = True
            elif child.type == "link_open":
                href = child.attrGet("href") or ""
                text_parts = []
            elif child.type == "link_close" and href:
                if seen_label:
                    return inline("".join(text_parts)), href
                href = ""
            elif href and child.type in {"code_inline", "image"}:
                text_parts.append(child.content)
        links = token_links(token)
        if links:
            return links[0]
    return "", ""


def extract_images(source: Source, tokens: list[Token]) -> list[str]:
    candidates: list[str] = []
    for token in tokens:
        if token.type == "inline":
            for child in token.children or []:
                if child.type == "image":
                    candidates.append(child.attrGet("src") or "")
                elif child.type == "html_inline":
                    candidates.extend(html_images(child.content))
        elif token.type == "html_block":
            candidates.extend(html_images(token.content))
    return unique(
        resolved
        for candidate in candidates
        if (resolved := absolute_url(source.url, candidate)) and not decorative_image(resolved)
    )


def html_images(value: str) -> list[str]:
    return [image.get("src", "") for image in BeautifulSoup(value, "html.parser").find_all("img")]


def decorative_image(value: str) -> bool:
    parsed = urlparse(value)
    return (
        parsed.hostname in {"img.shields.io", "awesome.re"}
        or "badge.svg" in parsed.path.lower()
        or "/actions/workflows/" in parsed.path.lower()
    )


def first_paragraph(tokens: list[Token], *, exclude: tuple[str, ...]) -> str:
    for token in tokens:
        if token.type != "inline":
            continue
        text = token_text(token)
        if text and not any(marker in text for marker in exclude) and not extract_inline_images(token):
            return text
    return ""


def extract_inline_images(token: Token) -> bool:
    return any(
        child.type == "image" or (child.type == "html_inline" and "<img" in child.content.lower())
        for child in token.children or []
    )


def paragraph_after_heading(tokens: list[Token], label: str) -> str:
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.type == "heading_open" and token.tag == "h4" and label in heading_text(tokens, index):
            for candidate in tokens[index + 3 :]:
                if candidate.type == "heading_open":
                    return ""
                if candidate.type == "inline":
                    return token_text(candidate)
            return ""
        index += 1
    return ""


def published_date(tokens: list[Token]) -> str:
    for token in tokens:
        if token.type != "inline":
            continue
        match = re.search(r"发布时间[:：]\s*(\d{4})年(\d{1,2})月(\d{1,2})日", token_text(token))
        if match:
            year, month, day = map(int, match.groups())
            return f"{year:04d}-{month:02d}-{day:02d}"
    return ""


def published_date_flexible(tokens: list[Token]) -> str:
    for token in tokens:
        if token.type not in {"inline", "html_block"}:
            continue
        value = token_text(token) if token.type == "inline" else token.content
        match = re.search(r"发布时间[:：]\s*[*_]*\s*(\d{4})年(\d{1,2})月(\d{1,2})日", value)
        if match:
            year, month, day = map(int, match.groups())
            return f"{year:04d}-{month:02d}-{day:02d}"
        match = re.search(r"发布时间[:：]\s*[*_]*\s*([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})", value)
        if match:
            month, day, year = match.groups()
            for format_code in ("%B %d %Y", "%b %d %Y"):
                try:
                    return datetime.strptime(f"{month} {day} {year}", format_code).date().isoformat()
                except ValueError:
                    continue
            return ""
    return ""


def clean_category(value: str) -> str:
    return re.sub(r"^[^\w]+", "", inline(value), flags=re.UNICODE)


PARSERS: dict[str, Callable[[Source, bytes], list[dict[str, Any]]]] = {
    "banana-json": parse_banana_json,
    "davidwu-json": parse_davidwu_json,
    "freestylefly-json": parse_freestylefly_json,
    "awesome-gpt-image-markdown": parse_awesome_gpt_image,
    "awesome-gpt4o-markdown": parse_awesome_gpt4o,
    "youmind-markdown": parse_youmind,
    "seedance-markdown": parse_seedance,
    "zerolu-nanobanana-markdown": parse_zerolu_nanobanana,
    "picotrex-markdown": parse_picotrex,
    "youmind-skill-midjourney": parse_youmind_skill_midjourney,
}

# Adapters whose source URL is a manifest; sync fetches the listed files and joins them
# into {"categories": [{"title": ..., "items": [...]}]} before parsing.
BUNDLES: dict[str, Callable[[Source, bytes], list[tuple[str, str]]]] = {
    "youmind-skill-midjourney": youmind_skill_files,
}
