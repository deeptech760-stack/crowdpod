# Adapted from the upstream project listed in NOTICE (AGPL-3.0); modified 2026-10-30.
"""Cleaning and parsing of model output that should be JSON."""

from __future__ import annotations

import json
import re
from typing import Any


class LLMResponseError(ValueError):
    """A safe, structured error for unusable model responses."""

    def __init__(self, message: str, *, finish_reason: str | None = None):
        super().__init__(message)
        self.finish_reason = finish_reason


def clean_chat_text(content: str) -> str:
    """Remove common reasoning wrappers and an outer Markdown JSON fence."""
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", content).strip()
    cleaned = cleaned.lstrip("﻿")
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    return cleaned.strip()


def contains_additional_json_container(content: str) -> bool:
    """Return True when trailing text embeds another JSON object or array."""
    decoder = json.JSONDecoder()
    for match in re.finditer(r"[\[{]", content):
        try:
            value, _ = decoder.raw_decode(content[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(value, (dict, list)):
            return True
    return False


def parse_json_object(content: str, *, finish_reason: str | None = None) -> dict[str, Any]:
    """Parse one top-level JSON object. Never repairs or invents truncated JSON."""
    content = clean_chat_text(content)
    if not content:
        raise LLMResponseError("LLM returned empty JSON content", finish_reason=finish_reason)
    try:
        value = json.loads(content)
    except json.JSONDecodeError as strict_error:
        # Some compatible providers append a short explanation after an
        # otherwise complete JSON object. Accept only an object decoded
        # from the beginning.
        try:
            value, end = json.JSONDecoder().raw_decode(content)
        except json.JSONDecodeError:
            raise LLMResponseError(
                f"LLM returned invalid JSON (line {strict_error.lineno}, column {strict_error.colno})",
                finish_reason=finish_reason,
            ) from strict_error
        trailing = content[end:].strip()
        if trailing and contains_additional_json_container(trailing):
            raise LLMResponseError("LLM returned multiple JSON values", finish_reason=finish_reason)
    if not isinstance(value, dict):
        raise LLMResponseError("LLM JSON response must be a top-level JSON object", finish_reason=finish_reason)
    return value


def coerce_to_str(value: Any) -> str:
    """Coerce a value to a plain string. Models sometimes return dicts or lists for text fields."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("text", "value", "description", "content", "summary", "name"):
            if key in value:
                candidate = coerce_to_str(value[key])
                if candidate:
                    return candidate
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        items = [coerce_to_str(item) for item in value]
        return ", ".join(item for item in items if item)
    return str(value)


def coerce_to_str_list(value: Any) -> list[str]:
    """Coerce a value to a list of strings, flattening nested lists."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        result: list[str] = []
        for item in value:
            if isinstance(item, (list, tuple)):
                result.extend(coerce_to_str_list(item))
            else:
                text = coerce_to_str(item)
                if text:
                    result.append(text)
        return result
    text = coerce_to_str(value)
    return [text] if text else []
