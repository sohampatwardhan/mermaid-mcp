"""JSON IR -> Mermaid source, via the serializers vendored from mermaid-skill."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from importlib import resources
from typing import Any

from .vendor import render as _upstream

IRError = _upstream.IRError


def from_ir(ir: dict[str, Any] | str, target: str | None = None) -> str:
    """Serialize an IR document to Mermaid. Raises IRError on any invalid input.

    Upstream raises IRError for schema violations, but a structurally wrong document
    (a string where a list belongs, a missing nested key) can surface as KeyError or
    TypeError from inside a serializer. Those are rejected the same way: nothing is
    emitted unless the whole document serialized.
    """
    if isinstance(ir, str):
        try:
            ir = json.loads(ir)
        except json.JSONDecodeError as exc:
            raise IRError(f"IR is not valid JSON: {exc}") from exc
    if not isinstance(ir, dict):
        raise IRError(f"IR must be a JSON object, got {type(ir).__name__}")
    try:
        return _upstream.render(ir, target=target)
    except IRError:
        raise
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        raise IRError(f"malformed IR ({type(exc).__name__}: {exc})") from exc


TARGETS: dict[str, str] = {target: family for family, target in _upstream.SERIALIZERS}


def resolve_target(name: str) -> tuple[str, str]:
    """Accept 'target' or 'family/target'; return (family, target)."""
    family, _, target = name.rpartition("/")
    if target not in TARGETS or (family and TARGETS[target] != family):
        raise IRError(f"unknown IR target {name!r}; call list_ir_targets for the supported list")
    return TARGETS[target], target


def list_targets() -> str:
    by_family: dict[str, list[str]] = {}
    for target, family in TARGETS.items():
        by_family.setdefault(family, []).append(target)
    lines = [f"{family}: {', '.join(targets)}" for family, targets in by_family.items()]
    return (
        'IR = {"diagram": <family>, "target": <target>, ...}. Families and targets:\n'
        + "\n".join(lines)
        + "\nCall list_ir_targets(target=...) for that target's fields."
    )


_HEADING = re.compile(r"^(#{2,3}) (.+)$", re.MULTILINE)
_TICKED = re.compile(r"`([^`]+)`")


@lru_cache(maxsize=1)
def _sections() -> list[tuple[str, str]]:
    """(heading, body) for every level-2/3 section of the vendored IR references."""
    out: list[tuple[str, str]] = []
    for name in ("ir.md", "ir-catalog.md"):
        text = resources.files("mermaid_mcp.reference").joinpath(name).read_text(encoding="utf-8")
        matches = list(_HEADING.finditer(text))
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            out.append((match.group(2), text[match.start():end].strip()))
    return out


def target_schema(name: str) -> str:
    """The reference section documenting one target.

    A heading naming the target after its family wins (e.g. "`graph` — `erDiagram`";
    the family token itself is skipped because `timeline` is both). Otherwise the
    family-only heading applies (e.g. "`graph` — nodes, edges" covers flowchart and
    mindmap; "`chart`" covers every chart target in one table).
    """
    family, target = resolve_target(name)
    sections = _sections()
    for heading, body in sections:
        if target in _TICKED.findall(heading)[1:]:
            return body
    for heading, body in sections:
        if _TICKED.findall(heading) == [family]:
            return body
    raise IRError(f"no schema section found for {family}/{target}")
