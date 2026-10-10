# Package Security Rules (uv)

> **🔒 HUMAN-OWNED POLICY — agents must not edit this file.** It is blocked by a
> deny rule in `.claude/settings.json`. If a change needs a policy change, propose
> the diff and let a human apply it. Never weaken a rule to make an install pass.

## Rules

1. **uv only.** No `pip install`, no `requirements.txt`, no other lockfiles.
2. **Commit `uv.lock`.** Install with `uv sync --locked`, which fails if the lockfile
   and `pyproject.toml` disagree.
3. **Pin exactly.** Every dependency in `pyproject.toml` uses `==`. Upgrade one
   package at a time (`uv lock --upgrade-package <name>`) and review the `uv.lock` diff.
4. **Quarantine new releases.** `exclude-newer = "7 days"` in `pyproject.toml`
   ignores anything published in the last 7 days, when most malicious releases are
   caught and pulled.
5. **Pin Python.** The version lives in `.python-version`.
6. **Non-PyPI sources need a reason.** Today only the spaCy language models come from
   `github.com/explosion/spacy-models` (they aren't on PyPI). `uv.lock` records their hashes.
7. **Check for known vulnerabilities** before releasing:
   `uvx --from pip-audit==2.9.0 pip-audit` (or any equivalent scanner).
