"""MCP server (stdio): from_ir, render, list_ir_targets."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import (
    BlobResourceContents,
    CallToolResult,
    EmbeddedResource,
    ImageContent,
    TextContent,
    ToolAnnotations,
)

from . import __version__, renderer
from . import ir as irlib

INSTRUCTIONS = """\
Mermaid diagrams from structured JSON IR, rendered with Mermaid CLI 12.
Workflow: list_ir_targets -> list_ir_targets(target) for fields -> from_ir(ir) -> render(ir=...).
Prefer IR over hand-written Mermaid whenever the content is structured (nodes/edges, steps,
states, rows). render(source=...) is for validating or displaying Mermaid you already have.
Invalid IR and Mermaid that fails to render are errors; nothing is silently dropped."""

server = MCPServer("mermaid-mcp", version=__version__, instructions=INSTRUCTIONS)

IRArg = dict[str, Any] | str


def _mermaid(ir_doc: IRArg, target: str | None) -> str:
    try:
        return irlib.from_ir(ir_doc, target=target)
    except irlib.IRError as exc:
        raise ToolError(f"invalid IR: {exc}") from exc


@server.tool(
    description=(
        "Convert diagram JSON IR to Mermaid source. Deterministic; fails on unknown kinds, "
        "missing fields, or undeclared ids. IR: {diagram, target, ...}; see list_ir_targets."
    ),
    annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False),
    structured_output=False,
)
def from_ir(ir: IRArg, target: str | None = None) -> str:
    """ir: IR object (or JSON string). target: optional override of ir.target."""
    return _mermaid(ir, target)


@server.tool(
    description=(
        "Validate and render a diagram with Mermaid CLI 12. Pass ir (preferred) or Mermaid source. "
        "Returns the Mermaid source plus PNG image (and SVG if requested). Fails on render errors."
    ),
    annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False),
)
def render(
    ir: IRArg | None = None,
    source: str | None = None,
    target: str | None = None,
    formats: list[Literal["png", "svg"]] | None = None,
    theme: Literal["default", "dark", "forest", "neutral"] | None = None,
    save_dir: str | None = None,
) -> CallToolResult:
    """ir or source (exactly one). formats default ["png"]. save_dir: also write files there."""
    if (ir is None) == (source is None):
        raise ToolError("pass exactly one of 'ir' or 'source'")
    mermaid = _mermaid(ir, target) if ir is not None else source
    assert mermaid is not None
    try:
        result = renderer.render(mermaid, tuple(formats or ("png",)), theme=theme)
    except renderer.RenderError as exc:
        raise ToolError(f"{exc}\n--- source ---\n{mermaid}") from exc

    meta: dict[str, Any] = {"source": result.source, "formats": sorted(result.images)}
    if result.warnings:
        meta["warnings"] = result.warnings
    if save_dir:
        meta["files"] = _save(result, Path(save_dir).expanduser())

    content: list[TextContent | ImageContent | EmbeddedResource] = [
        TextContent(type="text", text=json.dumps(meta, ensure_ascii=False))
    ]
    if "png" in result.images:
        content.append(ImageContent(type="image", data=_b64(result.images["png"]), mime_type="image/png"))
    if "svg" in result.images:
        content.append(
            EmbeddedResource(
                type="resource",
                resource=BlobResourceContents(
                    uri=f"mermaid://diagram/{_digest(result.source)}.svg",
                    mime_type="image/svg+xml",
                    blob=_b64(result.images["svg"]),
                ),
            )
        )
    return CallToolResult(content=content)


@server.tool(
    description="List supported IR targets, or pass target to get that target's IR fields and example.",
    annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False),
    structured_output=False,
)
def list_ir_targets(target: str | None = None) -> str:
    """target: e.g. 'flowchart' or 'graph/flowchart'."""
    if target is None:
        return irlib.list_targets()
    try:
        return irlib.target_schema(target)
    except irlib.IRError as exc:
        raise ToolError(str(exc)) from exc


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _digest(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]


def _save(result: renderer.RenderResult, directory: Path) -> dict[str, str]:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        stem = directory / f"diagram-{_digest(result.source)}"
        files = {"mmd": stem.with_suffix(".mmd")}
        files["mmd"].write_text(result.source, encoding="utf-8")
        for fmt, data in result.images.items():
            files[fmt] = stem.with_suffix(f".{fmt}")
            files[fmt].write_bytes(data)
    except OSError as exc:
        raise ToolError(f"could not write to save_dir {str(directory)!r}: {exc}") from exc
    return {fmt: str(path) for fmt, path in files.items()}


def main() -> None:
    server.run("stdio")
