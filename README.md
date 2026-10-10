# nopii-mcp

A local MCP server that lets Claude read your documents **without seeing the personal
data in them**. Put files in a folder; when Claude asks for one, nopii-mcp converts it
to markdown, replaces names, emails, phone numbers, addresses, IBANs, URLs and similar with
placeholders like `<PERSON_1>`, and returns only the redacted text.

```
~/pii-files/contract.pdf ──► Docling ──► Presidio + GLiNER ──► <PERSON_1> signed on … ──► Claude
                            (markdown)   (find & replace PII)
```

Everything runs on your machine. Nothing is uploaded except the redacted text Claude reads.
Supports English and German documents (detected automatically).

## Setup

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/) (macOS, Linux, Windows).

```bash
git clone https://github.com/olafrv/nopii-mcp
cd nopii-mcp
uv sync --locked
```

The first conversion downloads the AI models (over 1 GB, cached by Hugging Face).

## Run

```bash
uv run nopii-mcp                      # serves ~/pii-files on http://127.0.0.1:8765/mcp
uv run nopii-mcp --dir ~/some/folder  # serve another folder
uv run nopii-mcp --port 9000          # another port
uv run nopii-mcp warm                 # convert everything now, so Claude never waits
```

The server only ever listens on `127.0.0.1`. That address is hard-coded: the server has
no authentication, so it must not be reachable from the network.

## Connect Claude

**Claude Code** — start the server (above), then:

```bash
claude mcp add --scope user --transport http nopii http://127.0.0.1:8765/mcp
```

**Claude Desktop** — Desktop starts local servers itself, so no separate `uv run` is
needed. Add this to `claude_desktop_config.json` (Settings → Developer → Edit Config),
with your clone's path, and restart Claude Desktop:

```json
{
  "mcpServers": {
    "nopii": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/nopii-mcp", "nopii-mcp", "--stdio"]
    }
  }
}
```

Add `"--dir", "/some/folder"` to `args` to serve another folder. If Claude Desktop can't
find `uv`, use its full path (`which uv` / `where uv`).

## Tools Claude gets

| Tool | What it does |
|---|---|
| `list_files(subdir)` | Lists the files and whether each is `ready`, `converting`, `error` or `new` |
| `read_file(path, offset, limit)` | Returns redacted markdown, 40,000 characters at a time |

A big file can take minutes to convert the first time. `read_file` waits up to 20 seconds,
then tells Claude to try again shortly. Run `warm` beforehand to avoid the wait.

## How it works

| File | Job |
|---|---|
| `src/nopii_mcp/cli.py` | Command line |
| `src/nopii_mcp/server.py` | The MCP server and its two tools |
| `src/nopii_mcp/cache.py` | Converts each file once and remembers the result |
| `src/nopii_mcp/convert.py` | Any document → markdown with [Docling](https://github.com/docling-project/docling), images dropped |
| `src/nopii_mcp/redact.py` | Finds PII with [Presidio](https://github.com/microsoft/presidio) + [GLiNER](https://github.com/urchade/GLiNER) and replaces it |

**Redaction.** Presidio's pattern recognizers find structured values (emails, phones,
IBANs, credit cards, IPs, and all URLs, public ones included). GLiNER (`urchade/gliner_multi_pii-v1`) finds contextual ones
(names, addresses, ID numbers, dates of birth). Presidio feeds long documents to GLiNER in
overlapping chunks, so PII on page 50 is caught like PII on page 1. Placeholders are
numbered per document: the same person is always `<PERSON_1>` within one file. The real
values are never stored anywhere, so Claude's answers will contain the placeholders too.

**Cache** (`cache/` in the repo, git-ignored):

```
cache/nopii.db              which file has which content hash, and each hash's status
cache/raw/<sha256>.md       Docling output — unredacted, never sent to Claude
cache/redacted/<sha256>.md  what Claude receives
```

Files are identified by content hash, so renaming, moving or copying a file never causes
a second conversion. Claude Desktop and Claude Code can share one cache: SQLite ensures
only one of them converts a given file. To re-redact everything after changing
`redact.py`, delete `cache/redacted/` and `cache/nopii.db` (the raw markdown is reused,
so Docling doesn't run again).

## Development

```bash
uv run pytest                 # includes leak tests: PII hidden deep in long EN/DE documents
uv run ruff check src tests
```

Dependency rules: see [UV_SECURITY.md](UV_SECURITY.md).

## Known limitations

PII redaction relies on automatic entity detection, which is imperfect. It can
over-redact, hiding ordinary words, job titles, product or technology names and
dates, sometimes only part of a word, and so remove information that isn't personal.
It can also under-redact, missing names or identifiers, or catching a value in one
place but not another in the same document. Placeholders are assigned per document,
and different values may sometimes share one, so don't assume a placeholder always
means the same real-world entity. Only file contents are redacted: file and folder
names are returned as they are and can expose personal data. PDF conversion can also
lose layout, separating details such as dates or locations from the text they belong
to. Treat redacted output as a best effort that lowers exposure, not a guarantee that
no personal data remains, and check the results before relying on them.

## Other limits

- **Images are dropped**, including any text in them. Scanned PDFs are OCR'd into text,
  which is redacted like any other text.
- **Claude can bypass this server** if it has other ways to read your files. In Claude
  Code, add deny rules to your user settings (`~/.claude/settings.json`) so it can't read
  the originals or the raw cache directly:

  ```json
  { "permissions": { "deny": ["Read(~/pii-files/**)", "Read(/path/to/nopii-mcp/cache/raw/**)"] } }
  ```

  In Claude Desktop, don't attach the original files to a chat.
