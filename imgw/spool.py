"""Payloads saved while another process holds the database, ingested on the next run."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)


def save(payload: dict | list, spool_dir: Path, stamp: datetime) -> Path:
    """Write ``payload`` atomically, named by ``stamp`` so files sort oldest first."""
    spool_dir.mkdir(parents=True, exist_ok=True)
    path = spool_dir / f"{stamp:%Y%m%dT%H%M%S%f}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, path)
    return path


def drain(spool_dir: Path) -> Iterator[dict | list]:
    """Yield saved payloads oldest first.

    A file is deleted only once the caller asks for the next payload, so one whose
    ingest raised stays for the next run. Unreadable files are set aside as ``.bad``.
    """
    for path in sorted(spool_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            log.warning("unreadable spool file %s (%s), set aside", path.name, e)
            os.replace(path, path.with_suffix(".bad"))
            continue
        yield payload
        path.unlink()
