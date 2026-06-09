"""Treadwell AI News Feed — MCP server (read-only).

Wraps the News Feed REST API as MCP tools, cross-references surfaced projects
against the Dropbox estimating/project folders (read-only; files are copied to a
temp dir, parsed, then deleted — nothing in Dropbox is ever modified), and composes
grounded outreach drafts for the Gmail connector to turn into drafts.
"""

__version__ = "0.1.0"
