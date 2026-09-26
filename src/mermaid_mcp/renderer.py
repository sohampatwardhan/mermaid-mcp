"""Render Mermaid source with @mermaid-js/mermaid-cli, mirroring mermaid-skill's check.sh.

CLI resolution order: $MERMAID_MMDC (a command, shell-split), `mmdc` on PATH, then
`npx -y @mermaid-js/mermaid-cli@12.0.0`. Mermaid 11 does not register agentflow-beta or
usecase-beta, and mermaid-cli 12 needs Node >= 22.13.

Set MERMAID_PUPPETEER_CONFIG to a puppeteer JSON file (e.g. {"args": ["--no-sandbox"]})
where Chromium cannot get a sandbox (root in Docker, GitHub Actions ubuntu-latest).
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

MERMAID_CLI_PACKAGE = "@mermaid-js/mermaid-cli@12.0.0"
EXPECTED_MAJOR = "12"
FORMATS = ("png", "svg")
THEMES = ("default", "dark", "forest", "neutral")

# Mermaid CLI can exit 0 while writing its syntax-error placeholder SVG.
_ERROR_SVG = re.compile(r'aria-roledescription="error"|class="error-icon"|>Syntax error in text<', re.IGNORECASE)
_STACK_FRAME = re.compile(r"\(\S+:\d+:\d+\)\s*$")


class RenderError(Exception):
    pass


@dataclass
class RenderResult:
    source: str
    images: dict[str, bytes]
    cli: str
    warnings: list[str] = field(default_factory=list)


def is_error_svg(svg: str | bytes) -> bool:
    text = svg.decode("utf-8", errors="replace") if isinstance(svg, bytes) else svg
    return bool(_ERROR_SVG.search(text))


def resolve_cli() -> list[str]:
    override = os.environ.get("MERMAID_MMDC")
    if override:
        return shlex.split(override)
    mmdc = shutil.which("mmdc")
    if mmdc:
        return [mmdc]
    npx = shutil.which("npx")
    if npx:
        return [npx, "-y", os.environ.get("MERMAID_CLI_PACKAGE", MERMAID_CLI_PACKAGE)]
    raise RenderError(
        "no Mermaid CLI: install Node 22 and run `npm install -g @mermaid-js/mermaid-cli@12.0.0`, "
        "or set MERMAID_MMDC to the mmdc command"
    )


@lru_cache(maxsize=8)
def _version_warning(cli: tuple[str, ...]) -> str | None:
    if "-y" in cli:  # pinned npx package
        return None
    try:
        out = subprocess.run([*cli, "--version"], capture_output=True, text=True, timeout=60).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    if out.split(".")[0] != EXPECTED_MAJOR:
        return f"mmdc reports version {out or 'unknown'}; mermaid-mcp is tested against {MERMAID_CLI_PACKAGE}"
    return None


def _timeout() -> float:
    return float(os.environ.get("MERMAID_MCP_TIMEOUT", "120"))


def _summarize(output: str, limit: int = 1500) -> str:
    """Keep the Mermaid error message, drop the JS stack trace."""
    lines = [
        line for line in output.splitlines()
        if line.strip()
        and not line.lstrip().startswith("at ")
        and not _STACK_FRAME.search(line)
        and line.strip() != "Generating single mermaid chart"
    ]
    text = "\n".join(lines).strip()
    return text[:limit] + ("…" if len(text) > limit else "")


def render(
    source: str,
    formats: tuple[str, ...] | list[str] = ("png",),
    *,
    theme: str | None = None,
    background: str | None = None,
    scale: int = 2,
) -> RenderResult:
    """Validate by rendering to SVG, reject error placeholders, then produce each requested format."""
    if not source or not source.strip():
        raise RenderError("empty diagram source")
    unknown = [fmt for fmt in formats if fmt not in FORMATS]
    if unknown or not formats:
        raise RenderError(f"formats must be a non-empty subset of {list(FORMATS)}, got {list(formats)}")
    if theme is not None and theme not in THEMES:
        raise RenderError(f"theme must be one of {list(THEMES)}, got {theme!r}")

    cli = resolve_cli()
    warnings = [w for w in [_version_warning(tuple(cli))] if w]
    options: list[str] = []
    if theme:
        options += ["-t", theme]
    if background:
        options += ["-b", background]
    puppeteer = os.environ.get("MERMAID_PUPPETEER_CONFIG")
    if puppeteer:
        options += ["-p", puppeteer]

    with tempfile.TemporaryDirectory(prefix="mermaid-mcp-") as tmp:
        src = Path(tmp) / "in.mmd"
        src.write_text(source if source.endswith("\n") else source + "\n", encoding="utf-8")

        def run(out: Path, extra: list[str]) -> None:
            try:
                proc = subprocess.run(
                    [*cli, "-i", str(src), "-o", str(out), *options, *extra],
                    capture_output=True, text=True, timeout=_timeout(),
                )
            except subprocess.TimeoutExpired as exc:
                raise RenderError(f"mermaid-cli timed out after {exc.timeout:.0f}s") from exc
            except OSError as exc:
                raise RenderError(f"could not run {cli[0]!r}: {exc}") from exc
            if proc.returncode != 0 or not out.exists():
                detail = _summarize(proc.stderr + "\n" + proc.stdout) or f"exit code {proc.returncode}"
                raise RenderError(f"Mermaid could not render the diagram:\n{detail}")

        svg_path = Path(tmp) / "out.svg"
        run(svg_path, [])
        svg = svg_path.read_bytes()
        if is_error_svg(svg):
            raise RenderError(
                "Mermaid emitted an error SVG despite exiting 0. Beta diagram lexers may reject label "
                "punctuation (often ':') that other diagram types accept; check the source against "
                "list_ir_targets(target=...) or prefer from_ir."
            )

        images: dict[str, bytes] = {}
        if "svg" in formats:
            images["svg"] = svg
        if "png" in formats:
            png_path = Path(tmp) / "out.png"
            run(png_path, ["-s", str(scale)])
            images["png"] = png_path.read_bytes()

    return RenderResult(source=source, images=images, cli=" ".join(cli), warnings=warnings)
