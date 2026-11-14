"""Network access in one place, so offline mode is a single switch."""
from __future__ import annotations

import time

import httpx

from . import config

_last_check = {"t": 0.0, "online": False}


def is_online(force_check: bool = False) -> bool:
    if config.FORCE_OFFLINE:
        return False
    now = time.time()
    if not force_check and now - _last_check["t"] < 30:
        return _last_check["online"]
    try:
        httpx.head("https://api.nasa.gov/", timeout=3.0)
        ok = True
    except Exception:
        ok = False
    _last_check.update(t=now, online=ok)
    return ok


def get(url: str, params: dict | None = None, timeout: float = 20.0) -> httpx.Response:
    if config.FORCE_OFFLINE:
        raise ConnectionError("MARSPATH_OFFLINE=1: network disabled")
    r = httpx.get(url, params=params, timeout=timeout, follow_redirects=True,
                  headers={"User-Agent": "MarsPath/1.0 (NASA Space Apps 2026 prototype)"})
    r.raise_for_status()
    return r
