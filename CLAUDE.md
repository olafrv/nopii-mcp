# nopii-mcp

Local MCP server that gives Claude PII-redacted markdown of the user's files.
See README.md for how it works.

## Package management — MANDATORY

`UV_SECURITY.md` is binding policy. Read it before any change to dependencies,
`pyproject.toml` or `uv.lock`, and obey every rule. It is human-owned: do not edit
it; propose the diff instead.

## Rules for this codebase

- `HOST` in `src/nopii_mcp/server.py` stays hard-coded to `127.0.0.1`. Never make it
  configurable: the server has no auth.
- Never read `cache/raw/` — it holds unredacted documents.
- Keep the code short: one job per module (`server` → `cache` → `convert`, `redact`).
- Run `uv run pytest` and `uv run ruff check src tests` before finishing a change.
