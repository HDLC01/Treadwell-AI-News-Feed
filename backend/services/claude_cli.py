"""
Claude integration via the local **Claude Code CLI** (`claude -p`).

Uses the local Claude CLI instead of the Anthropic SDK, so the backend needs no
ANTHROPIC_API_KEY — it piggybacks on the logged-in Claude subscription (the same
pattern the Treadwell proposal tool uses in its container, with the login persisted
on a Docker volume at /root/.claude).

Public API:
    call_claude(user_prompt, system="", timeout=120) -> str
        Returns the model's plain-text response. Raises ClaudeCLIError on
        CLI-not-installed / non-zero exit / timeout / non-JSON output.

    parse_loose_json(text) -> dict | list | None
        Tolerant JSON parser: strips ```json fences before json.loads.

    call_claude_json(user_prompt, system="", timeout=120) -> dict | list | None
        Convenience: call_claude + parse_loose_json. Returns None if the model
        produced no parseable JSON (callers must handle the None / fallback path).
"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile

log = logging.getLogger("newsfeed.claude")

# Spawn `claude` from a clean temp dir so it does NOT inherit this project's
# CLAUDE.md (that file is meta-instructions for human collaboration; injecting
# it into every backend call would bias responses and waste cache tokens).
_CLEAN_CWD = tempfile.mkdtemp(prefix="newsfeed-claude-")


class ClaudeCLIError(RuntimeError):
    """Raised when the local `claude` CLI fails."""


def call_claude(user_prompt: str, system: str = "", *, timeout: int = 120) -> str:
    full_prompt = f"{system}\n\n{user_prompt}" if system else user_prompt

    try:
        result = subprocess.run(
            ["claude", "-p", "--output-format", "json"],
            input=full_prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=_CLEAN_CWD,
            timeout=timeout,
            shell=False,
        )
    except FileNotFoundError as exc:
        raise ClaudeCLIError(
            "`claude` CLI not found on PATH. Install Claude Code: "
            "https://docs.claude.com/claude-code"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ClaudeCLIError(f"Claude CLI call timed out (>{timeout}s).") from exc

    if result.returncode != 0:
        raise ClaudeCLIError(
            f"Claude CLI failed (exit {result.returncode}): {result.stderr.strip()}"
        )

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ClaudeCLIError(
            f"Claude CLI returned non-JSON: {result.stdout[:500]!r}"
        ) from exc

    if payload.get("is_error"):
        raise ClaudeCLIError(f"Claude CLI reported error: {payload!r}")

    return (payload.get("result") or "").strip()


def parse_loose_json(text: str):
    """Strip ```json fences (if any) and json.loads. Returns dict/list or None."""
    text = (text or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Last resort: try to salvage the outermost {...} or [...] block.
        for open_ch, close_ch in (("{", "}"), ("[", "]")):
            start = text.find(open_ch)
            end = text.rfind(close_ch)
            if start != -1 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    pass
        return None


def call_claude_json(user_prompt: str, system: str = "", *, timeout: int = 120):
    """call_claude + parse_loose_json. Returns dict/list, or None on any failure.

    Never raises for the no-JSON case — pipeline services depend on a graceful
    None so a single bad extraction can't kill a daily run.
    """
    try:
        raw = call_claude(user_prompt, system, timeout=timeout)
    except ClaudeCLIError as exc:
        log.warning("claude -p call failed: %s", exc)
        return None
    return parse_loose_json(raw)
