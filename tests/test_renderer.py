from __future__ import annotations

import pytest

from mermaid_mcp import ir, renderer

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_error_svg_detection() -> None:
    assert renderer.is_error_svg('<svg aria-roledescription="error">')
    assert renderer.is_error_svg(b'<g class="error-icon"/>')
    assert renderer.is_error_svg("<text>Syntax error in text</text>")
    assert not renderer.is_error_svg('<svg aria-roledescription="flowchart-v2">')


def test_placeholder_svg_is_rejected_even_on_exit_0(fake_mmdc) -> None:
    fake_mmdc("placeholder")
    with pytest.raises(renderer.RenderError, match="error SVG"):
        renderer.render("flowchart TD\n  A-->B\n", ("png", "svg"))


def test_cli_failure_reports_message_without_stack(fake_mmdc) -> None:
    fake_mmdc("fail")
    with pytest.raises(renderer.RenderError) as info:
        renderer.render("flowchart TD\n  A-->\n")
    assert "Parse error on line 2" in str(info.value)
    assert "Object.parse" not in str(info.value)


def test_fake_cli_success_and_argument_validation(fake_mmdc) -> None:
    result = renderer.render("flowchart TD\n  A-->B\n", ("svg", "png"))
    assert set(result.images) == {"svg", "png"}
    assert result.warnings == []
    for bad in ({"formats": ("gif",)}, {"formats": ()}, {"theme": "neon"}):
        with pytest.raises(renderer.RenderError):
            renderer.render("flowchart TD\n  A-->B\n", **bad)
    with pytest.raises(renderer.RenderError, match="empty"):
        renderer.render("   ")


def test_resolution_prefers_override_then_mmdc_then_npx(monkeypatch) -> None:
    monkeypatch.setenv("MERMAID_MMDC", "/opt/mmdc --quiet")
    assert renderer.resolve_cli() == ["/opt/mmdc", "--quiet"]
    monkeypatch.delenv("MERMAID_MMDC")
    monkeypatch.setattr(renderer.shutil, "which", lambda name: "/usr/bin/npx" if name == "npx" else None)
    assert renderer.resolve_cli() == ["/usr/bin/npx", "-y", "@mermaid-js/mermaid-cli@12.0.0"]
    monkeypatch.setattr(renderer.shutil, "which", lambda name: None)
    with pytest.raises(renderer.RenderError, match="no Mermaid CLI"):
        renderer.resolve_cli()


# --- real Mermaid CLI 12 ------------------------------------------------------------------


def test_real_render_png_and_svg(real_cli) -> None:
    source = ir.from_ir({
        "diagram": "sequence", "target": "sequenceDiagram",
        "actors": [{"id": "User"}, {"id": "API"}],
        "steps": [{"from": "User", "to": "API", "label": "GET /health"},
                  {"from": "API", "to": "User", "label": "200 OK", "kind": "reply"}],
    })
    result = renderer.render(source, ("png", "svg"))
    assert result.images["png"].startswith(PNG_MAGIC)
    assert b"<svg" in result.images["svg"]
    assert not renderer.is_error_svg(result.images["svg"])
    assert result.warnings == []


def test_real_render_mermaid_12_only_types(real_cli) -> None:
    source = ir.from_ir({
        "diagram": "graph", "target": "agentflow-beta",
        "nodes": [{"id": "plan", "label": "Plan", "kind": "task"}, {"id": "act", "label": "Act", "kind": "tool"}],
        "edges": [{"from": "plan", "to": "act"}],
    })
    assert renderer.render(source, ("svg",)).images["svg"]


def test_real_placeholder_svg_is_rejected(real_cli) -> None:
    # mermaid-cli 12.0.0 exits 0 here but writes Mermaid's error placeholder SVG.
    with pytest.raises(renderer.RenderError, match="error SVG"):
        renderer.render("wardley-beta\n  component A: [0.5, 0.5]\n", ("svg",))


def test_real_syntax_error_is_rejected(real_cli) -> None:
    with pytest.raises(renderer.RenderError, match="could not render"):
        renderer.render("flowchart TD\n  A-->\n")
