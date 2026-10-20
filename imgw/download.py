"""HTTP access to IMGW with retries, a polite delay and a local ZIP cache."""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path

import httpx

from .config import BASE_URL

log = logging.getLogger(__name__)

USER_AGENT = "daneimgw-local-mirror/0.1 (personal use)"


def client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=httpx.Timeout(60.0, connect=15.0),
        follow_redirects=True,
        transport=httpx.HTTPTransport(retries=3),
    )


def fetch(c: httpx.Client, url: str, attempts: int = 4, delay: float = 0.0) -> bytes:
    for i in range(attempts):
        try:
            r = c.get(url)
            r.raise_for_status()
            if delay:
                time.sleep(delay)
            return r.content
        except (httpx.HTTPError, httpx.StreamError) as e:
            if i == attempts - 1:
                raise
            wait = 2 ** i * 2
            log.warning("GET %s failed (%s), retry in %ss", url, e, wait)
            time.sleep(wait)
    raise AssertionError("unreachable")


def cache_path(raw_dir: Path, url: str) -> Path:
    rel = url.removeprefix(BASE_URL).lstrip("/")
    return raw_dir / rel


def fetch_cached(
    c: httpx.Client, url: str, raw_dir: Path, keep: bool, refresh: bool, delay: float
) -> tuple[bytes, str]:
    """Return (content, sha256). Reuses the cached file unless ``refresh``."""
    path = cache_path(raw_dir, url)
    if path.exists() and not refresh:
        data = path.read_bytes()
    else:
        data = fetch(c, url, delay=delay)
        if keep:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    return data, hashlib.sha256(data).hexdigest()
