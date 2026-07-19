#!/usr/bin/env python3
"""Canonical identity shared by MURAL projection, structural union, and fusion."""

from __future__ import annotations

from typing import Any


def normalized_path(value: object) -> str:
    path = str(value or "").replace("\\", "/")
    if path.startswith(("a/", "b/")):
        path = path[2:]
    while path.startswith("./"):
        path = path[2:]
    return path


def qualified_symbol_base(value: object) -> str:
    return str(value or "").split(" = ", 1)[0].split("(", 1)[0].strip()


def entity_kind(item: dict[str, Any]) -> str:
    explicit = str(item.get("entity_type") or "").lower()
    source = str(item.get("source_code") or "").lstrip()
    signature = str(item.get("signature") or item.get("name") or "")
    if explicit == "class" or source.startswith("class "):
        return "class"
    if explicit == "assignment" or (
        " = " in signature and not source.startswith(("def ", "async def "))
    ):
        return "assignment"
    return "function"


def canonical_entity_id(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        normalized_path(item.get("file_path")),
        entity_kind(item),
        qualified_symbol_base(item.get("signature") or item.get("name")),
    )


def canonical_entity_key(item: dict[str, Any]) -> str:
    identity = canonical_entity_id(item)
    if not identity[0] or not identity[2]:
        return ""
    return "|".join(identity)


def canonicalize_ranked_entities(
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in entities:
        identity = canonical_entity_id(item)
        if not identity[0] or not identity[2] or identity in seen:
            continue
        seen.add(identity)
        output.append(item)
    return output
