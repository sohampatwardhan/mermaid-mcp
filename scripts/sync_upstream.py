#!/usr/bin/env python3
"""Refresh the vendored IR layer from sohampatwardhan/mermaid-skill.

Copies the upstream files listed in FILES verbatim and records the upstream commit and
each file's sha256 in src/mermaid_mcp/vendor/UPSTREAM.json. tests/test_vendor.py fails
if a vendored file no longer matches that manifest, so local edits cannot drift silently.

Usage:
    scripts/sync_upstream.py              # pull upstream main
    scripts/sync_upstream.py --ref v1.2   # pull a tag, branch, or commit
    scripts/sync_upstream.py --check      # exit 1 if upstream differs from the vendored copy

Set GITHUB_TOKEN (or GH_TOKEN) to avoid API rate limits.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path

REPO = "sohampatwardhan/mermaid-skill"
ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "src" / "mermaid_mcp" / "vendor" / "UPSTREAM.json"

# upstream path -> local path (relative to repo root)
FILES = {
    "mermaid/scripts/render.py": "src/mermaid_mcp/vendor/render.py",
    "mermaid/reference/ir.md": "src/mermaid_mcp/reference/ir.md",
    "mermaid/reference/ir-catalog.md": "src/mermaid_mcp/reference/ir-catalog.md",
    "mermaid/reference/coverage.md": "src/mermaid_mcp/reference/coverage.md",
    "mermaid/tests/test_render.py": "tests/upstream/tests/test_render.py",
}


def _get(url: str, accept: str | None = None) -> bytes:
    headers = {"User-Agent": "mermaid-mcp-sync"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token and "api.github.com" in url:
        headers["Authorization"] = f"Bearer {token}"
    if accept:
        headers["Accept"] = accept
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as resp:
        return resp.read()


def resolve_commit(ref: str) -> str:
    sha = _get(f"https://api.github.com/repos/{REPO}/commits/{ref}", accept="application/vnd.github.sha")
    return sha.decode().strip()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ref", default="main", help="Upstream branch, tag, or commit (default: main).")
    parser.add_argument("--check", action="store_true", help="Report drift without writing files.")
    args = parser.parse_args(argv)

    commit = resolve_commit(args.ref)
    fetched = {
        upstream: _get(f"https://raw.githubusercontent.com/{REPO}/{commit}/{upstream}")
        for upstream in FILES
    }

    if args.check:
        drift = [
            upstream
            for upstream, data in fetched.items()
            if not (ROOT / FILES[upstream]).exists() or (ROOT / FILES[upstream]).read_bytes() != data
        ]
        if drift:
            print(f"Upstream {REPO}@{commit[:12]} differs from the vendored copy:")
            for upstream in drift:
                print(f"  {upstream} -> {FILES[upstream]}")
            print("Run scripts/sync_upstream.py, then pytest, and review the diff.")
            return 1
        print(f"Vendored files match {REPO}@{commit[:12]}.")
        return 0

    for upstream, data in fetched.items():
        local = ROOT / FILES[upstream]
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(data)
        print(f"wrote {FILES[upstream]}")

    manifest = {
        "repo": REPO,
        "ref": args.ref,
        "commit": commit,
        "files": {FILES[upstream]: sha256(data) for upstream, data in fetched.items()},
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Pinned {REPO}@{commit} in {MANIFEST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
