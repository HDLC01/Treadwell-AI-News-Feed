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

SECURITY: every prompt sent from here carries UNTRUSTED text. Signal
extraction, relevance scoring, clustering and contact enrichment all feed the
model scraped web pages, articles and search results, so anyone who can get a
page into a source can write instructions into it. The subprocess is therefore
a text-in/JSON-out transform with no way to act. It is locked down the way the
proposal tool locks down its autofill call:

  * `--tools ""` registers no built-in tools (no Bash, Read, Write, WebFetch).
    This is not a permission rule: the tools do not exist in the session, so no
    prompt or settings file can grant them back. Measured on the proposal
    tool's call of the same shape: without it, `claude -p` reads a file and
    runs a shell command on request. Here that would happen as root, inside a
    container that holds the Supabase service-role key.
  * `--strict-mcp-config` with no `--mcp-config` loads zero MCP servers, so a
    server configured on the /root/.claude volume cannot hand this session
    tools either.
  * The prompt goes on stdin and argv is a constant. Untrusted text never lands
    in a flag or a system prompt.
  * `env=_cli_env()` gives the child an allowlist: PATH, HOME, locale and the
    CLI's own login. The Supabase keys, the Resend key, the JWT secret, the
    connector's API key and every other app setting stay in this process.
  * Each call runs in a fresh, empty temp directory that is deleted afterwards,
    so the CLI finds no CLAUDE.md, .mcp.json or .claude/settings.json, and
    nothing one call leaves behind can reach the next. `--no-session-persistence`
    stops each of those one-off directories leaving a transcript of scraped
    text on the credentials volume, and the empty per-directory project
    folder the CLI still creates there is removed after the call.
  * `timeout` bounds every call.

Do NOT add `--bare`. It skips hooks and CLAUDE.md, which sounds right, but it
also stops the CLI reading the OAuth login this container authenticates with,
and every AI stage of the pipeline would go dark.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
from typing import Dict

log = logging.getLogger("newsfeed.claude")

# The exact command. Constant on purpose: nothing from a prompt is ever spliced
# in, and the tests pin it. `--tools` takes a variable number of values, so the
# empty string must be followed by another flag to land as its only value.
_CLAUDE_ARGV = (
    "claude", "-p",
    "--tools", "",
    "--strict-mcp-config",
    "--no-session-persistence",
    "--output-format", "json",
)

# What the child process is allowed to see from our environment. An allowlist,
# not a scrub: in production `env_file: .env` puts every secret this app has
# into os.environ, so anything not named here stays behind, including secrets
# nobody has added yet. Compared upper-cased because Windows (local dev)
# upper-cases environment names.
_CLI_ENV_KEEP = frozenset({
    # Find `node` and `claude`; find ~/.claude, where `claude login` keeps the
    # credentials on the claude_credentials volume.
    "PATH", "HOME", "USER", "LOGNAME", "TMPDIR", "TZ", "LANG", "LANGUAGE",
    # The CLI's own login, and where its config lives when moved off ~/.claude.
    # The ANTHROPIC_* names are kept so the CLI picks the same credential and
    # endpoint it picks today; dropping one would silently change which account
    # is billed or where the call goes.
    "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CONFIG_DIR",
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
    # On a host behind a proxy or a private CA the CLI cannot reach the API
    # without these.
    "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY",
    "NODE_EXTRA_CA_CERTS", "SSL_CERT_FILE", "SSL_CERT_DIR",
    # Windows (local dev only): the home directory, Winsock and temp paths
    # node resolves at startup, and the Git Bash the Windows CLI looks for.
    "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT",
    "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA",
    "TEMP", "TMP", "PROGRAMFILES", "PROGRAMDATA",
    "CLAUDE_CODE_GIT_BASH_PATH",
})
_CLI_ENV_KEEP_PREFIXES = ("LC_",)   # locale: LC_ALL, LC_CTYPE, ...


def _cli_env() -> Dict[str, str]:
    """The allowlisted slice of our environment, for the `claude` child."""
    return {
        k: v for k, v in os.environ.items()
        if k.upper() in _CLI_ENV_KEEP
        or k.upper().startswith(_CLI_ENV_KEEP_PREFIXES)
    }


# The CLI keeps per-project state in <config dir>/projects/<slug>, where <slug>
# is the working directory with every character outside [A-Za-z0-9] turned into
# "-" (that rule is read out of the shipped CLI binary). It keys on the git root
# instead when the directory sits inside a repo, which a temp dir in the
# container does not. With --no-session-persistence it writes no transcript
# there, but it still creates an empty <slug>/memory folder. Every call has a
# new cwd, so without cleanup every AI call would leave one more empty folder on
# the persistent credentials volume, forever.
_SLUG_UNSAFE = re.compile(r"[^a-zA-Z0-9]")


def _cli_project_dirs(cwd: str, env: Dict[str, str]) -> list:
    """Where the CLI files its project state for a session started in `cwd`.

    The same config dir the child resolves (CLAUDE_CONFIG_DIR, else ~/.claude,
    and the child's HOME is ours). Both the path as given and its resolved form,
    because the CLI slugs the directory it finds itself in, which can differ
    from the path we passed when the temp dir sits behind a symlink."""
    config = env.get("CLAUDE_CONFIG_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude")
    slugs = {_SLUG_UNSAFE.sub("-", p) for p in (cwd, os.path.realpath(cwd))}
    return [os.path.join(config, "projects", s) for s in sorted(slugs)]


def _remove_empty_dirs(top: str) -> None:
    """rmdir `top` and the folders under it, bottom-up, each only if empty.

    os.rmdir refuses a directory that still holds anything, so this never
    deletes a file: if the CLI ever does write something there, it stays."""
    for root, _dirs, _files in os.walk(top, topdown=False):
        try:
            os.rmdir(root)
        except OSError:
            pass


class ClaudeCLIError(RuntimeError):
    """Raised when the local `claude` CLI fails."""


def call_claude(user_prompt: str, system: str = "", *, timeout: int = 120) -> str:
    full_prompt = f"{system}\n\n{user_prompt}" if system else user_prompt

    try:
        # A fresh empty directory per call (see SECURITY above). It also keeps
        # this project's CLAUDE.md out of every call: that file is instructions
        # for human collaboration and would bias the answers.
        with tempfile.TemporaryDirectory(prefix="newsfeed-claude-",
                                         ignore_cleanup_errors=True) as cwd:
            env = _cli_env()
            try:
                result = subprocess.run(
                    list(_CLAUDE_ARGV),
                    input=full_prompt,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=cwd,
                    env=env,
                    timeout=timeout,
                    shell=False,
                )
            finally:
                # Also after a timeout: run() has killed and reaped the child.
                for project_dir in _cli_project_dirs(cwd, env):
                    _remove_empty_dirs(project_dir)
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
