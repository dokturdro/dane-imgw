"""Walk the IMGW archive's Apache directory listings."""

from __future__ import annotations

import html
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date

import httpx

from .config import BASE_URL
from .download import fetch

_ROW = re.compile(
    r'<a href="(?P<href>[^"?/][^"]*)">[^<]*</a></td>'
    r'<td[^>]*>(?P<mtime>[^<]*)</td><td[^>]*>(?P<size>[^<]*)</td>'
)
_YEAR_DIR = re.compile(r"^(\d{4})(?:_(\d{4}))?/$")

# (resolution, network) -> archive path
SECTIONS = {
    ("daily", "synop"): "dobowe/synop",
    ("daily", "klimat"): "dobowe/klimat",
    ("daily", "opad"): "dobowe/opad",
    ("hourly", "synop"): "terminowe/synop",
    ("hourly", "klimat"): "terminowe/klimat",
}


@dataclass(frozen=True)
class RemoteFile:
    url: str
    resolution: str      # daily | hourly
    network: str         # synop | klimat | opad
    first_year: int
    last_year: int
    fingerprint: str     # "<mtime>|<size>" from the listing

    @property
    def name(self) -> str:
        return self.url.rsplit("/", 1)[-1]


def list_dir(client: httpx.Client, url: str) -> list[tuple[str, str, str]]:
    """Return [(href, mtime, size)] for one listing page."""
    text = fetch(client, url).decode("utf-8", errors="replace")
    return [
        (html.unescape(m["href"]), m["mtime"].strip(), m["size"].strip())
        for m in _ROW.finditer(text)
    ]


def walk(
    client: httpx.Client,
    resolution: str,
    network: str,
    start_year: int,
    end_year: int | None = None,
) -> Iterator[RemoteFile]:
    end_year = end_year or date.today().year
    base = f"{BASE_URL}/{SECTIONS[resolution, network]}/"
    for href, _mtime, _size in list_dir(client, base):
        m = _YEAR_DIR.match(href)
        if not m:
            continue
        y0 = int(m[1])
        y1 = int(m[2] or m[1])
        if y1 < start_year or y0 > end_year:
            continue
        for fname, mtime, size in list_dir(client, base + href):
            if fname.lower().endswith(".zip"):
                yield RemoteFile(
                    url=base + href + fname,
                    resolution=resolution,
                    network=network,
                    first_year=y0,
                    last_year=y1,
                    fingerprint=f"{mtime}|{size}",
                )
