"""The cache converts each distinct content once, no matter the file name."""

from nopii_mcp import cache as cache_module
from nopii_mcp.cache import Cache


def test_same_content_converted_once(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(cache_module.redact, "redact", lambda text: calls.append(text) or "REDACTED")

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.txt").write_text("hello", encoding="utf-8")
    (docs / "copy-of-a.txt").write_text("hello", encoding="utf-8")
    cache = Cache(tmp_path / "cache")

    sha_a = cache.hash_file(docs / "a.txt")
    sha_copy = cache.hash_file(docs / "copy-of-a.txt")
    assert sha_a == sha_copy

    cache.start(docs / "a.txt", sha_a).result()
    assert cache.status(sha_a) == ("done", None)
    assert cache.start(docs / "copy-of-a.txt", sha_copy) is None  # already done
    assert cache.read(sha_a) == "REDACTED"
    assert len(calls) == 1


def test_changed_file_gets_new_hash(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("one", encoding="utf-8")
    cache = Cache(tmp_path / "cache")
    first = cache.hash_file(path)
    path.write_text("two, longer", encoding="utf-8")
    assert cache.hash_file(path) != first


def test_failed_conversion_is_recorded_and_retried(tmp_path, monkeypatch):
    def boom(text):
        raise RuntimeError("model missing")

    monkeypatch.setattr(cache_module.redact, "redact", boom)
    path = tmp_path / "a.txt"
    path.write_text("hello", encoding="utf-8")
    cache = Cache(tmp_path / "cache")
    sha = cache.hash_file(path)

    job = cache.start(path, sha)
    assert job.exception() is not None
    assert cache.status(sha) == ("error", "RuntimeError: model missing")
    assert cache.start(path, sha) is not None  # errors may be retried


def test_abandoned_conversion_can_be_taken_over(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("hello", encoding="utf-8")
    cache = Cache(tmp_path / "cache")
    sha = cache.hash_file(path)
    assert cache._claim(sha)  # another process claimed it...
    assert not cache._claim(sha)  # ...so nobody else may, while its heartbeat is fresh
    with cache._db() as db:  # ...then it crashed and the heartbeat went stale
        db.execute("UPDATE documents SET updated = updated - ?", (cache_module.STALE_AFTER + 1,))
    assert cache._claim(sha)
