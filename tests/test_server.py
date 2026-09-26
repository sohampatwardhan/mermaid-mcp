from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
from pathlib import Path
from typing import Any

from mcp import Client, StdioServerParameters

from mermaid_mcp.server import server

FLOWCHART = {
    "diagram": "graph", "target": "flowchart",
    "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B", "kind": "decision"}],
    "edges": [{"from": "a", "to": "b"}],
}


def call(name: str, arguments: dict[str, Any]):
    async def go():
        async with Client(server) as client:
            return await client.call_tool(name, arguments)

    return asyncio.run(go())


def test_tool_surface_is_lean() -> None:
    async def go():
        async with Client(server) as client:
            return await client.list_tools()

    tools = {tool.name: tool for tool in asyncio.run(go()).tools}
    assert set(tools) == {"from_ir", "render", "list_ir_targets"}
    for tool in tools.values():
        assert len(tool.description or "") < 250


def test_from_ir_returns_mermaid_text() -> None:
    result = call("from_ir", {"ir": FLOWCHART})
    assert not result.is_error
    assert result.content[0].text.startswith("flowchart TD\n")
    assert "shape: diamond" in result.content[0].text


def test_from_ir_invalid_ir_is_a_clear_tool_error() -> None:
    bad = {**FLOWCHART, "edges": [{"from": "a", "to": "ghost"}]}
    result = call("from_ir", {"ir": bad})
    assert result.is_error
    assert "invalid IR" in result.content[0].text
    assert "undeclared node" in result.content[0].text


def test_list_ir_targets() -> None:
    listing = call("list_ir_targets", {}).content[0].text
    assert "graph: flowchart" in listing
    schema = call("list_ir_targets", {"target": "sequenceDiagram"}).content[0].text
    assert "activate" in schema
    assert call("list_ir_targets", {"target": "nope"}).is_error


def test_render_requires_exactly_one_input(fake_mmdc) -> None:
    assert call("render", {}).is_error
    assert call("render", {"ir": FLOWCHART, "source": "flowchart TD\n A-->B"}).is_error


def test_render_from_ir_returns_source_image_and_svg(fake_mmdc, tmp_path: Path) -> None:
    result = call("render", {"ir": FLOWCHART, "formats": ["png", "svg"], "save_dir": str(tmp_path)})
    assert not result.is_error
    meta = json.loads(result.content[0].text)
    assert meta["source"].startswith("flowchart TD")
    assert meta["formats"] == ["png", "svg"]
    image = result.content[1]
    assert image.type == "image" and image.mime_type == "image/png"
    assert base64.b64decode(image.data).startswith(b"\x89PNG")
    svg = result.content[2].resource
    assert svg.mime_type == "image/svg+xml"
    assert Path(meta["files"]["png"]).exists() and Path(meta["files"]["mmd"]).read_text() == meta["source"]


def test_render_rejects_placeholder_and_echoes_source(fake_mmdc) -> None:
    fake_mmdc("placeholder")
    result = call("render", {"source": "flowchart TD\n  A-->B"})
    assert result.is_error
    assert "error SVG" in result.content[0].text
    assert "A-->B" in result.content[0].text


def test_render_invalid_ir_never_reaches_the_cli(fake_mmdc) -> None:
    fake_mmdc("fail")
    result = call("render", {"ir": {"diagram": "graph", "target": "flowchart", "nodes": []}})
    assert result.is_error and "invalid IR" in result.content[0].text


def test_stdio_transport_like_an_mcp_host() -> None:
    params = StdioServerParameters(command=sys.executable, args=["-m", "mermaid_mcp"], env=dict(os.environ))

    async def go():
        async with Client(params) as client:
            tools = await client.list_tools()
            result = await client.call_tool("from_ir", {"ir": FLOWCHART})
            return {tool.name for tool in tools.tools}, result

    names, result = asyncio.run(go())
    assert names == {"from_ir", "render", "list_ir_targets"}
    assert result.content[0].text.startswith("flowchart TD")


def test_render_real_cli_end_to_end(real_cli) -> None:
    result = call("render", {"ir": FLOWCHART})
    assert not result.is_error, result.content[0].text
    assert base64.b64decode(result.content[1].data).startswith(b"\x89PNG")
