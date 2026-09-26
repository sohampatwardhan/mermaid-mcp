"""Shim: the vendored upstream test suite loads ../scripts/render.py; point it at the packaged copy."""

from mermaid_mcp.vendor.render import *  # noqa: F401,F403
from mermaid_mcp.vendor.render import IRError, SERIALIZERS, render  # noqa: F401
