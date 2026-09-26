"""The vendored IR layer must stay byte-identical to the pinned mermaid-skill commit."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from mermaid_mcp import renderer

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "src/mermaid_mcp/vendor/UPSTREAM.json").read_text())


def test_vendored_files_match_manifest() -> None:
    assert re.fullmatch(r"[0-9a-f]{40}", MANIFEST["commit"])
    for path, digest in MANIFEST["files"].items():
        actual = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        assert actual == digest, f"{path} was edited locally; re-run scripts/sync_upstream.py instead"


def test_ci_pins_the_same_mermaid_cli() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    assert renderer.MERMAID_CLI_PACKAGE in workflow
    assert 'node-version: "22"' in workflow
