"""Allowlisted HTML/text ingestion. Network content stays draft until a person reviews it."""

import hashlib
import ipaddress
import socket
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import requests

from core.evidence import stable_id
from core.schemas import SourceRecord


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skipped = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "template"}:
            self.skipped += 1
        if not self.skipped and tag in {"p", "div", "br", "h1", "h2", "h3", "li"}:
            self.parts.append("\n\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "template"}:
            self.skipped = max(0, self.skipped - 1)

    def handle_data(self, data):
        if not self.skipped:
            self.parts.append(data)


def validate_source_url(url, policy):
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    if (
        parsed.scheme != "https"
        or parsed.port not in {None, 443}
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Source must use HTTPS without credentials and with the standard port")
    if not any(host == domain or host.endswith("." + domain) for domain in policy.allowed_domains):
        raise ValueError("Source domain is not allowlisted")
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(
        not ipaddress.ip_address(address[4][0]).is_global for address in addresses
    ):
        raise ValueError("Source must resolve only to public IP addresses")
    return host


def fetch_source(url, policy):
    deadline = time.monotonic() + policy.timeout_seconds
    for _ in range(policy.max_redirects + 1):
        host = validate_source_url(url, policy)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise requests.Timeout("Source deadline exceeded")
        with requests.get(
            url,
            timeout=remaining,
            allow_redirects=False,
            stream=True,
            headers={"User-Agent": "HeritageVQA/0.2 (research prototype)"},
        ) as response:
            if response.status_code in {301, 302, 303, 307, 308}:
                url = urljoin(url, response.headers["Location"])
                continue
            response.raise_for_status()
            mime = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if mime not in {"text/html", "text/plain", "application/xhtml+xml"}:
                raise ValueError("Only HTML/plain text is supported; PDF needs a separate parser")
            content = bytearray()
            for chunk in response.iter_content(16384):
                if time.monotonic() > deadline:
                    raise requests.Timeout("Source deadline exceeded")
                content.extend(chunk)
                if len(content) > policy.max_document_bytes:
                    raise ValueError("Source exceeds the document size limit")
            encoding = (
                response.encoding
                if response.encoding and response.encoding.lower() != "iso-8859-1"
                else "utf-8"
            )
            text = content.decode(encoding, errors="replace")
            if mime != "text/plain":
                parser = PlainText()
                parser.feed(text)
                text = "".join(parser.parts)
            text = "\n\n".join(" ".join(p.split()) for p in text.split("\n\n") if p.strip())
            if not text:
                raise ValueError("Source has no readable text")
            version = hashlib.sha256(text.encode()).hexdigest()
            return SourceRecord(
                source_id=stable_id("web", {"url": url, "content_hash": version}),
                title=host + " — " + urlsplit(url).path[:200],
                url=url,
                type="web",
                snippet=text,
                content_hash=version,
                locator=f"chars:0:{len(text)}",
                publisher=host,
                retrieved_at=datetime.now(timezone.utc).isoformat(),
                annotation_status="draft",
            ).model_dump(mode="json")
    raise ValueError("Source redirect limit exceeded")
