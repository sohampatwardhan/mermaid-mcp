#!/usr/bin/env bash
# Shim: the vendored upstream test suite calls ../scripts/check.sh; route it through
# this package's renderer so upstream IR tests exercise the same path as the MCP render tool.
exec "${MERMAID_MCP_PYTHON:-python3}" -m mermaid_mcp check "$@"
