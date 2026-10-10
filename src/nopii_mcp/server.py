"""The MCP server: two tools that give Claude PII-redacted markdown of your files."""

from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from .cache import Cache

# Hard-coded on purpose: this server has no auth, so it must never listen on the network.
HOST = "127.0.0.1"
WAIT_SECONDS = 20  # how long read_file waits for a fresh conversion before answering "converting"
DEFAULT_LIMIT = 40_000

INSTRUCTIONS = """Serves documents from the user's PII folder as markdown with personal data
replaced by placeholders like <PERSON_1> or <EMAIL_ADDRESS_2>. Placeholders are numbered per
document. Treat them as opaque names; the original values are never available."""


def build(root: Path, cache: Cache) -> MCPServer:
    root = root.resolve()
    mcp = MCPServer("nopii", instructions=INSTRUCTIONS, log_level="WARNING")

    def resolve(path: str) -> Path:
        full = (root / path).resolve()
        if not full.is_relative_to(root) or not full.is_file():
            raise ValueError(f"No such file: {path}")
        return full

    @mcp.tool()
    def list_files(subdir: str = "") -> str:
        """List files in the PII folder (or a subfolder), with their conversion status:
        ready (cached), converting, error, or new (read_file will convert it)."""
        base = (root / subdir).resolve()
        if not base.is_relative_to(root) or not base.is_dir():
            raise ValueError(f"No such folder: {subdir}")
        lines = []
        for path in sorted(base.rglob("*")):
            rel = path.relative_to(root)
            if not path.is_file() or any(part.startswith(".") for part in rel.parts):
                continue
            sha = cache.known_hash(path)
            status, _ = cache.status(sha) if sha else (None, None)
            label = {"done": "ready", None: "new"}.get(status, status)
            lines.append(f"{rel.as_posix()}\t{label}\t{path.stat().st_size} bytes")
        return "\n".join(lines) or "(no files)"

    @mcp.tool()
    def read_file(path: str, offset: int = 0, limit: int = DEFAULT_LIMIT) -> str:
        """Read a file from the PII folder as redacted markdown, `limit` characters from
        `offset`. The first read of a file converts it, which can take a while for big
        documents; if the answer says it is converting, call read_file again shortly."""
        full = resolve(path)
        sha = cache.hash_file(full)
        status, error = cache.status(sha)
        if status != "done":
            job = cache.start(full, sha)
            if job is not None:
                try:
                    job.result(timeout=WAIT_SECONDS)
                except Exception:
                    pass  # timeout: still converting; failure: recorded in the cache. Both reported below.
            status, error = cache.status(sha)
        if status == "error":
            return f"Converting {path} failed: {error}. Calling read_file again retries it."
        if status != "done":
            return f"{path} is still being converted. Call read_file again in a minute."

        text = cache.read(sha)
        end = min(offset + limit, len(text))
        footer = f"\n\n<!-- nopii: characters {offset}-{end} of {len(text)}"
        footer += f"; call read_file with offset={end} for more -->" if end < len(text) else " -->"
        return text[offset:end] + footer

    return mcp


def serve(root: Path, cache: Cache, port: int, stdio: bool) -> None:
    mcp = build(root, cache)
    if stdio:
        mcp.run("stdio")
        return
    # Reject requests whose Host/Origin isn't this machine (blocks DNS-rebinding from web pages).
    security = TransportSecuritySettings(
        allowed_hosts=[f"{HOST}:{port}", f"localhost:{port}"],
        allowed_origins=[f"http://{HOST}:{port}", f"http://localhost:{port}"],
    )
    mcp.run("streamable-http", host=HOST, port=port, transport_security=security)
