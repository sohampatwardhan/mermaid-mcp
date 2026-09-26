"""mermaid-mcp command line.

    mermaid-mcp                         run the MCP server on stdio (same as `serve`)
    mermaid-mcp from-ir diagram.json    IR -> Mermaid on stdout (like mermaid-skill render.py)
    mermaid-mcp check diagram.mmd       render-validate (like mermaid-skill check.sh)
    mermaid-mcp check -c 'flowchart TD; A-->B' -o out.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, ir, renderer


def _from_ir(args: argparse.Namespace) -> int:
    try:
        text = args.ir_file.read_text(encoding="utf-8") if str(args.ir_file) != "-" else sys.stdin.read()
        source = ir.from_ir(text, target=args.target)
    except (ir.IRError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.output:
        args.output.write_text(source, encoding="utf-8")
    else:
        sys.stdout.write(source)
    return 0


def _check(args: argparse.Namespace) -> int:
    if args.code is not None:
        source = args.code
    elif args.input is not None:
        if not args.input.is_file():
            print(f"ERROR: file not found: {args.input}")
            return 2
        source = args.input.read_text(encoding="utf-8")
    elif not sys.stdin.isatty():
        source = sys.stdin.read()
    else:
        print("ERROR: no input. Pass a file, -c '<code>', or pipe via stdin.")
        return 2
    if not source.strip():
        print("ERROR: empty diagram.")
        return 2

    fmt = "svg"
    if args.output is not None:
        fmt = args.output.suffix.lstrip(".").lower()
        if fmt not in renderer.FORMATS:
            print(f"ERROR: output must end in .png or .svg, got {args.output}")
            return 2
    try:
        result = renderer.render(source, (fmt,))
    except renderer.RenderError as exc:
        print(f"FAIL: {exc}")
        return 3 if str(exc).startswith("no Mermaid CLI") else 1
    for warning in result.warnings:
        print(f"warning: {warning}")
    print("PASS: diagram renders cleanly.")
    if args.output is not None:
        args.output.write_bytes(result.images[fmt])
        print(f"Wrote {args.output}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mermaid-mcp", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=f"mermaid-mcp {__version__}")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("serve", help="Run the MCP server on stdio.")

    p_ir = sub.add_parser("from-ir", help="Convert an IR JSON file ('-' for stdin) to Mermaid.")
    p_ir.add_argument("ir_file", type=Path)
    p_ir.add_argument("--target", default=None)
    p_ir.add_argument("-o", "--output", type=Path, default=None)

    p_check = sub.add_parser("check", help="Render-validate Mermaid source with Mermaid CLI 12.")
    p_check.add_argument("input", nargs="?", type=Path, default=None)
    p_check.add_argument("-c", "--code", default=None)
    p_check.add_argument("-o", "--output", type=Path, default=None, help="Write .png or .svg here.")

    args = parser.parse_args(argv)
    if args.command == "from-ir":
        return _from_ir(args)
    if args.command == "check":
        return _check(args)

    from .server import main as serve

    serve()
    return 0
