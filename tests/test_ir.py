from __future__ import annotations

import json

import pytest

from mermaid_mcp import ir
from mermaid_mcp.vendor import render as upstream

FLOWCHART = {
    "diagram": "graph", "target": "flowchart", "direction": "LR",
    "nodes": [{"id": "1.1", "label": "Start", "kind": "terminator"}, {"id": "b", "label": "Work"}],
    "edges": [{"from": "1.1", "to": "b", "label": "go"}],
}


def test_matches_upstream_output_exactly() -> None:
    assert ir.from_ir(FLOWCHART) == upstream.render(FLOWCHART)
    assert ir.from_ir(FLOWCHART).startswith("flowchart LR\n")


def test_accepts_json_string() -> None:
    assert ir.from_ir(json.dumps(FLOWCHART)) == upstream.render(FLOWCHART)


def test_target_override() -> None:
    doc = {**FLOWCHART, "target": "swimlane-beta"}
    assert ir.from_ir(doc).startswith("swimlane-beta LR")
    assert ir.from_ir(doc, target="flowchart").startswith("flowchart LR")


@pytest.mark.parametrize(
    "bad",
    [
        "{not json",
        "[1, 2]",
        {"target": "flowchart", "nodes": [], "edges": []},
        {"diagram": "graph", "target": "nope", "nodes": [], "edges": []},
        {"diagram": "graph", "target": "flowchart", "nodes": [{"id": "a", "label": "A"}],
         "edges": [{"from": "a", "to": "ghost"}]},
        {"diagram": "graph", "target": "flowchart", "nodes": "a,b", "edges": []},
        {"diagram": "graph", "target": "flowchart", "nodes": [{"id": "a", "label": "A", "kind": "blob"}],
         "edges": []},
        {"diagram": "sequence", "target": "sequenceDiagram", "actors": [{"id": "A"}],
         "steps": [{"type": "message", "from": "A", "to": "B", "label": "hi"}]},
    ],
)
def test_invalid_ir_fails_closed(bad) -> None:
    with pytest.raises(ir.IRError):
        ir.from_ir(bad)


def test_every_serializer_is_listed() -> None:
    listing = ir.list_targets()
    for family, target in upstream.SERIALIZERS:
        assert target in listing
        assert ir.resolve_target(target) == (family, target)
        assert ir.resolve_target(f"{family}/{target}") == (family, target)


@pytest.mark.parametrize("pair", list(upstream.SERIALIZERS), ids=lambda p: f"{p[0]}/{p[1]}")
def test_every_target_has_a_schema_section(pair) -> None:
    family, target = pair
    section = ir.target_schema(target)
    assert section.startswith("#")
    assert f"`{family}`" in section.splitlines()[0]


def test_schema_picks_the_specific_section() -> None:
    assert "dateFormat" in ir.target_schema("gantt")
    assert "`timeline` — `timeline`" in ir.target_schema("timeline")
    assert "sync" in ir.target_schema("sequenceDiagram")
    assert "crow" in ir.target_schema("erDiagram")


def test_unknown_or_mismatched_target_is_rejected() -> None:
    with pytest.raises(ir.IRError):
        ir.resolve_target("nope")
    with pytest.raises(ir.IRError):
        ir.resolve_target("chart/flowchart")
