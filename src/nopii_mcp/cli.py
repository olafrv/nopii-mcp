"""Command line: `nopii-mcp` serves the folder, `nopii-mcp warm` converts it all ahead of time."""

import argparse
import sys
from pathlib import Path

from .cache import Cache

CACHE_DIR = Path(__file__).resolve().parents[2] / "cache"  # <repo>/cache, next to src/


def main() -> None:
    parser = argparse.ArgumentParser(prog="nopii-mcp", description=__doc__)
    parser.add_argument("command", nargs="?", choices=["serve", "warm"], default="serve")
    parser.add_argument("--dir", type=Path, default=Path.home() / "pii-files", help="folder to serve")
    parser.add_argument("--port", type=int, default=8765, help="HTTP port on 127.0.0.1")
    parser.add_argument("--stdio", action="store_true", help="talk over stdin/stdout (Claude Desktop)")
    args = parser.parse_args()

    root = args.dir.expanduser()
    root.mkdir(parents=True, exist_ok=True)
    cache = Cache(CACHE_DIR)

    if args.command == "warm":
        warm(root, cache)
    else:
        from .server import serve

        print(f"nopii-mcp serving {root}", file=sys.stderr)
        serve(root, cache, args.port, args.stdio)


def warm(root: Path, cache: Cache) -> None:
    """Convert every file now, so Claude never has to wait."""
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if not path.is_file() or any(part.startswith(".") for part in rel.split("/")):
            continue
        sha = cache.hash_file(path)
        if cache.status(sha)[0] == "done":
            print(f"cached     {rel}")
            continue
        job = cache.start(path, sha)
        if job is None:
            print(f"busy       {rel} (another process is converting it)")
            continue
        try:
            job.result()
            print(f"converted  {rel}")
        except Exception as e:
            print(f"failed     {rel}: {e}")


if __name__ == "__main__":
    main()
