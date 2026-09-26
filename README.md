# mermaid-mcp

An MCP server that lets agents build Mermaid diagrams from **structured JSON IR** instead of
hand-writing Mermaid syntax, then **renders** them to PNG/SVG with Mermaid CLI 12 so the host
app can show the result.

The IR layer is copied verbatim from
[sohampatwardhan/mermaid-skill](https://github.com/sohampatwardhan/mermaid-skill) (`render.py`
and its schema docs), so the guardrails match the skill exactly. The skill does not need to
be installed. Same JSON in, same Mermaid out. Invalid IR fails closed: an unknown `kind`, a
missing field, or an edge to an undeclared node is an error, never a silent drop.

## Tools

| Tool | Input | Output |
|---|---|---|
| `from_ir` | `ir` (object or JSON string), optional `target` override | Mermaid source text |
| `render` | exactly one of `ir` (preferred) or `source`; optional `formats` (`["png"]` default, add `"svg"`), `theme`, `save_dir` | JSON text `{source, formats, files?, warnings?}`, a PNG image block, and an SVG resource block if requested |
| `list_ir_targets` | optional `target` (`"flowchart"` or `"graph/flowchart"`) | all families/targets, or the IR fields and example for one target |

Agent workflow: `list_ir_targets` → `list_ir_targets(target=…)` → `render(ir=…)`. Use
`from_ir` alone when you only need the Mermaid text (e.g. to paste into Markdown).
`render(source=…)` validates and displays Mermaid you already have. It is not a way to skip
the IR when the content is structured.

`render` always renders to SVG first and rejects Mermaid's **error-placeholder SVG**, which
mermaid-cli sometimes writes while still exiting 0. On any failure the tool returns an error
with Mermaid's message (no JS stack trace) and the offending source.

There are 38 targets across `graph` (flowchart, mindmap, block, C4 ×5, architecture-beta,
erDiagram, classDiagram, swimlane-beta, agentflow-beta, wardley-beta), `sequence`
(sequenceDiagram, zenuml), `state-machine`, `timeline` (gantt, timeline), `requirement-links`,
`chart` (pie, xychart, sankey, quadrantChart, radar-beta, treemap-beta, venn-beta), `packet`,
`board` (kanban), `journey`, `git`, `tree`, `cynefin`, `eventmodeling`, `grammar`, `usecase`, and
`info`. Full schemas are in [`src/mermaid_mcp/reference/`](src/mermaid_mcp/reference/). Known gaps
per type are in [`coverage.md`](src/mermaid_mcp/reference/coverage.md).

### Example

```json
{
  "diagram": "graph", "target": "flowchart", "direction": "LR",
  "nodes": [
    { "id": "start", "label": "Request", "kind": "terminator" },
    { "id": "ok", "label": "Valid?", "kind": "decision" },
    { "id": "db", "label": "Orders", "kind": "store" }
  ],
  "edges": [
    { "from": "start", "to": "ok" },
    { "from": "ok", "to": "db", "label": "yes" }
  ]
}
```

`from_ir` returns:

```
flowchart LR
  start@{ shape: stadium, label: "Request" }
  ok@{ shape: diamond, label: "Valid?" }
  db@{ shape: cyl, label: "Orders" }
  start --> ok
  ok -->|"yes"| db
```

Change `"to": "db"` to `"to": "dbx"` and the call fails with
`invalid IR: graph/flowchart edge references undeclared node: {...}`.

## Requirements

- Python 3.10+
- For `render`: Node **22.13+** and **`@mermaid-js/mermaid-cli@12.0.0`**. Mermaid 11 does not
  register `agentflow-beta` or `usecase-beta`, and mermaid-cli 12 needs Node 22.

The server uses `$MERMAID_MMDC` if set, then `mmdc` on `PATH`, then
`npx -y @mermaid-js/mermaid-cli@12.0.0`. The npx fallback downloads the CLI and Chromium on
the first render, which can exceed a host's tool timeout. Install it once instead:

```bash
npm install -g @mermaid-js/mermaid-cli@12.0.0
mmdc --version   # 12.0.0
```

If `mmdc` on `PATH` is not 12.x, `render` still runs but adds a warning to its result.
`from_ir` and `list_ir_targets` need no Node at all.

## Install

This package is not on PyPI yet. Run it straight from GitHub with [uv](https://docs.astral.sh/uv/):

```bash
uvx --from git+https://github.com/sohampatwardhan/mermaid-mcp mermaid-mcp --version
```

Or install it into an environment:

```bash
pip install git+https://github.com/sohampatwardhan/mermaid-mcp
# or, from a clone:
pip install -e ".[test]"
```

## Connect it to an MCP host

The server speaks MCP over **stdio**. The command is `mermaid-mcp`, or
`uvx --from git+https://github.com/sohampatwardhan/mermaid-mcp mermaid-mcp` without installing.

### Cursor

`~/.cursor/mcp.json` (all projects) or `.cursor/mcp.json` (one project):

```json
{
  "mcpServers": {
    "mermaid": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/sohampatwardhan/mermaid-mcp", "mermaid-mcp"]
    }
  }
}
```

If you installed with pip, use `"command": "mermaid-mcp"` and drop `args`.

### Claude Code

```bash
claude mcp add --scope user mermaid -- \
  uvx --from git+https://github.com/sohampatwardhan/mermaid-mcp mermaid-mcp
claude mcp list   # mermaid ... Connected
```

### Claude Desktop and other hosts

Use the same `command` / `args` as the Cursor example in the host's MCP config (for Claude
Desktop, `claude_desktop_config.json` → `mcpServers`). Pass settings through the host's `env`
block:

```json
"env": { "MERMAID_PUPPETEER_CONFIG": "/path/to/puppeteer.json" }
```

## Configuration

| Variable | Purpose |
|---|---|
| `MERMAID_MMDC` | Mermaid CLI command to use, e.g. `/opt/mmdc/node_modules/.bin/mmdc` |
| `MERMAID_CLI_PACKAGE` | npx fallback package (default `@mermaid-js/mermaid-cli@12.0.0`) |
| `MERMAID_PUPPETEER_CONFIG` | puppeteer JSON passed to `mmdc -p`. Use `{"args": ["--no-sandbox"]}` when Chromium has no sandbox (root in Docker, GitHub Actions) |
| `MERMAID_MCP_TIMEOUT` | seconds per mmdc run (default 120) |

## Command line

The same code paths are available without an MCP host, mirroring the skill's scripts:

```bash
mermaid-mcp from-ir diagram.json > diagram.mmd      # like render.py ("-" reads stdin)
mermaid-mcp check diagram.mmd -o diagram.png        # like check.sh (.png or .svg)
mermaid-mcp check -c 'flowchart TD; A-->B'
mermaid-mcp                                         # run the MCP server on stdio
```

`check` exits 0 on a clean render, 1 on a render failure or error SVG, 2 on bad input, and 3
when no Mermaid CLI is found.

## Keeping the IR in sync with mermaid-skill

Upstream files live unmodified in `src/mermaid_mcp/vendor/render.py`,
`src/mermaid_mcp/reference/*.md`, and `tests/upstream/tests/test_render.py`.
`src/mermaid_mcp/vendor/UPSTREAM.json` pins the upstream commit and each file's sha256.
`tests/test_vendor.py` fails if any of them is edited by hand.

```bash
python scripts/sync_upstream.py --check   # does upstream main differ from the vendored copy?
python scripts/sync_upstream.py           # pull main (or --ref <tag|branch|sha>) and re-pin
pytest                                    # includes the upstream test suite, unmodified
```

Review the diff, especially new targets. `list_ir_targets` picks up new serializers and
schema sections automatically. The **Upstream drift** workflow runs `--check` weekly.

## Development and verification

```bash
pip install -e ".[test]"
npm install -g @mermaid-js/mermaid-cli@12.0.0
MERMAID_MCP_REQUIRE_RENDER=1 pytest -q
```

The suite covers:

- **IR:** the wrapper matches upstream output byte for byte, and invalid IR fails closed.
  Every target resolves to a schema section.
- **Upstream parity:** mermaid-skill's own `test_render.py`. Its `check.sh` calls go through a
  shim into this package's renderer, so every upstream case is really rendered by mermaid-cli 12.
- **Renderer:** real PNG/SVG output and Mermaid-12-only types (`agentflow-beta`). A real
  mermaid-cli 12.0.0 exit-0 error SVG (`wardley-beta` with `:` in a label) is rejected, and
  CLI resolution order is checked.
- **MCP:** tool listing and calls over an in-memory client and over real stdio, including
  error results and image blocks.

Without a Mermaid CLI, tests that need a real render are skipped unless
`MERMAID_MCP_REQUIRE_RENDER=1` is set. CI sets it, installs the pinned CLI on Node 22, and
tests Python 3.10 and 3.13.

## License

MIT, same as mermaid-skill.
