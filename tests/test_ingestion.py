import pytest

from core.config import RetrievalPolicy
from core.ingestion import fetch_source, validate_source_url


def public_dns(monkeypatch):
    monkeypatch.setattr(
        "core.ingestion.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )


def test_source_fetch_checks_hosts_private_addresses_and_redirects(monkeypatch):
    policy = RetrievalPolicy(allowed_domains=["heritage.example"])
    public_dns(monkeypatch)
    for url in (
        "http://heritage.example/",
        "https://user@heritage.example/",
        "https://evil.example/",
        "https://heritage.example:8000/",
    ):
        with pytest.raises(ValueError):
            validate_source_url(url, policy)
    monkeypatch.setattr(
        "core.ingestion.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("127.0.0.1", 443))],
    )
    with pytest.raises(ValueError, match="public IP"):
        validate_source_url("https://heritage.example/", policy)
    public_dns(monkeypatch)

    class Redirect:
        status_code = 302
        headers = {"Location": "https://evil.example/"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr("core.ingestion.requests.get", lambda *args, **kwargs: Redirect())
    with pytest.raises(ValueError, match="allowlisted"):
        fetch_source("https://heritage.example/", policy)


def test_source_fetch_is_bounded_versioned_and_keeps_draft_status(monkeypatch):
    public_dns(monkeypatch)

    class Response:
        status_code = 200
        headers = {"Content-Type": "text/html; charset=utf-8"}
        encoding = "utf-8"
        content = (
            b"<h1>Test fixture</h1><script>malicious script</script><p>Documented fixture text.</p>"
        )

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def raise_for_status(self):
            pass

        def iter_content(self, *args):
            yield self.content

    monkeypatch.setattr("core.ingestion.requests.get", lambda *args, **kwargs: Response())
    policy = RetrievalPolicy(allowed_domains=["heritage.example"])
    result = fetch_source("https://heritage.example/source", policy)
    assert result["annotation_status"] == "draft" and len(result["content_hash"]) == 64
    assert "Documented fixture" in result["snippet"] and "malicious script" not in result["snippet"]
    Response.content = b"x" * 2000
    with pytest.raises(ValueError, match="size limit"):
        fetch_source(
            "https://heritage.example/source",
            policy.model_copy(update={"max_document_bytes": 1024}),
        )
