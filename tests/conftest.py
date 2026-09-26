from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path

import pytest

from mermaid_mcp import renderer

# tests/upstream/scripts/check.sh re-enters this interpreter.
os.environ.setdefault("MERMAID_MCP_PYTHON", sys.executable)


@pytest.fixture
def real_cli() -> list[str]:
    """Skip when no Mermaid CLI is available, unless MERMAID_MCP_REQUIRE_RENDER=1 (CI)."""
    try:
        return renderer.resolve_cli()
    except renderer.RenderError as exc:
        if os.environ.get("MERMAID_MCP_REQUIRE_RENDER") == "1":
            pytest.fail(str(exc))
        pytest.skip(str(exc))


FAKE_MMDC = textwrap.dedent(
    """
    import sys
    from pathlib import Path
    args = sys.argv[1:]
    if "--version" in args:
        print("12.0.0"); sys.exit(0)
    out = Path(args[args.index("-o") + 1])
    mode = Path(__file__).with_suffix(".mode").read_text().strip()
    if mode == "fail":
        print("Error: Parse error on line 2:\\n    at Object.parse (x.js:1:1)", file=sys.stderr)
        sys.exit(1)
    if out.suffix == ".svg":
        body = '<g aria-roledescription="error"></g>' if mode == "placeholder" else "<g>ok</g>"
        out.write_text(f'<svg xmlns="http://www.w3.org/2000/svg">{body}</svg>')
    else:
        out.write_bytes(b"\\x89PNG\\r\\n\\x1a\\nfake")
    """
)


@pytest.fixture
def fake_mmdc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A stand-in mmdc. Call the returned setter with 'ok', 'fail', or 'placeholder'."""
    script = tmp_path / "fake_mmdc.py"
    script.write_text(FAKE_MMDC)
    monkeypatch.setenv("MERMAID_MMDC", f'"{sys.executable}" "{script}"')

    def set_mode(mode: str) -> None:
        script.with_suffix(".mode").write_text(mode)

    set_mode("ok")
    return set_mode
