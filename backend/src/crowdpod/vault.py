"""Reads archetypes and prompt templates from the Obsidian vault."""

from __future__ import annotations

import copy
import re
from functools import cached_property
from pathlib import Path
from typing import Any

import yaml

from .models import Archetype, Persona

_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)
_PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def split_note(text: str) -> tuple[dict[str, Any], str]:
    """Split a Markdown note into (frontmatter dict, body)."""
    m = _FRONTMATTER.match(text.lstrip("﻿"))
    if not m:
        return {}, text.strip()
    meta = yaml.safe_load(m.group(1)) or {}
    if not isinstance(meta, dict):
        raise ValueError("frontmatter must be a mapping")
    return meta, m.group(2).strip()


def render(template: str, values: dict[str, Any]) -> str:
    """Fill {{name}} placeholders. Unknown placeholders are an error, so typos surface early."""

    def sub(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in values:
            raise KeyError(f"template placeholder {{{{{key}}}}} has no value")
        return str(values[key])

    return _PLACEHOLDER.sub(sub, template)


class Vault:
    def __init__(self, root: Path):
        self.root = Path(root)
        if not (self.root / "personas" / "archetypes").is_dir():
            raise FileNotFoundError(f"no personas/archetypes folder in vault {self.root}")

    @cached_property
    def archetypes(self) -> dict[str, Archetype]:
        found: dict[str, Archetype] = {}
        for path in sorted((self.root / "personas" / "archetypes").glob("*.md")):
            meta, body = split_note(path.read_text(encoding="utf-8"))
            if meta.get("type") != "archetype":
                continue
            meta = {k: v for k, v in meta.items() if k not in ("type", "links")}
            arch = Archetype(**meta, body=body, source=path.relative_to(self.root).as_posix())
            if arch.id in found:
                raise ValueError(f"duplicate archetype id {arch.id!r} in {path}")
            found[arch.id] = arch
        if not found:
            raise ValueError(f"no archetype notes in {self.root}")
        return found

    def extended(self, extra: dict[str, Archetype]) -> "Vault":
        """A view of this vault that also knows a run's generated archetypes."""
        view = copy.copy(self)
        view.__dict__["archetypes"] = {**self.archetypes, **extra}
        return view

    def template(self, name: str) -> str:
        _, body = split_note((self.root / "templates" / f"{name}.md").read_text(encoding="utf-8"))
        return body

    def persona_system_prompt(self, persona: Persona) -> str:
        arch = self.archetypes[persona.archetype_id]
        return render(
            self.template("persona-system"),
            {
                **persona.model_dump(),
                "tech_comfort": f"{persona.tech_comfort:.2f}",
                "body": arch.body,
            },
        )
