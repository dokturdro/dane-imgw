"""Settings from config.toml (project root), with defaults."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/dane_meteorologiczne"
LIVE_SYNOP_URL = "https://danepubliczne.imgw.pl/api/data/synop"
LIVE_METEO_URL = "https://danepubliczne.imgw.pl/api/data/meteo"


@dataclass
class Config:
    db_path: Path = ROOT / "data" / "imgw.duckdb"
    raw_dir: Path = ROOT / "data" / "raw"
    live_spool_dir: Path = ROOT / "data" / "live_spool"   # polls made while the DB was busy
    live_keep_days: int = 400          # drop raw live rows older than this
    start_year: int = 1991
    hourly_start_year: int = 1991
    networks: list[str] = field(default_factory=lambda: ["synop", "klimat", "opad"])
    hourly_networks: list[str] = field(default_factory=lambda: ["synop"])
    keep_raw: bool = True              # keep downloaded ZIPs in raw_dir
    request_delay: float = 0.2         # seconds between archive requests
    normal_period: tuple[int, int] = (1991, 2020)
    hot_period: tuple[int, int] = (1981, 2020)


def load(path: Path | None = None) -> Config:
    path = path or ROOT / "config.toml"
    cfg = Config()
    if path.exists():
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        for k, v in data.items():
            if not hasattr(cfg, k):
                raise ValueError(f"unknown config key {k!r} in {path}")
            cur = getattr(cfg, k)
            if isinstance(cur, Path):
                v = Path(v) if Path(v).is_absolute() else ROOT / v
            elif isinstance(cur, tuple):
                v = tuple(v)
            setattr(cfg, k, v)
    return cfg
