"""Radiation & space-weather context for EVA planning.

Two clearly separated parts:
1. DONKI (NASA CCMC) event catalogue: solar energetic particle events (SEP), flares (FLR) and
   coronal mass ejections (CME). Fetched online and cached with its date for offline use.
   DONKI is a heliophysics catalogue mostly observed from near Earth: an event listed there
   may or may not reach Mars. It is used as an ADVISORY, never as a Mars dose.
2. A measured reference: the Curiosity RAD average dose-equivalent rate on the surface of
   Gale crater (Hassler et al. 2014). It is a historical reference at another site, never a
   live or Jezero-specific value.
"""
from __future__ import annotations

import datetime as dt
import json
import re

from . import config, netutil

CACHE = config.CACHE_DIR / "donki.json"
_last_failure = {"t": 0.0, "error": None}
RETRY_AFTER_S = 300  # after a failed fetch, wait 5 min before trying again (DEMO_KEY allows ~30 calls/hour)
DONKI = "https://api.nasa.gov/DONKI/{kind}"

RAD_REFERENCE = {
    "value": 0.67,
    "unit": "mSv/day",
    "quantity": "average galactic cosmic ray dose equivalent rate on the surface",
    "where": "Gale crater (Curiosity rover), not Jezero",
    "period": "August 2012 - June 2013",
    "instrument": "MSL Radiation Assessment Detector (RAD)",
    "source_title": "Hassler et al. (2014), Mars' Surface Radiation Environment Measured with the Mars Science "
                    "Laboratory's Curiosity Rover, Science 343, doi:10.1126/science.1244797",
    "source_url": "https://www.swri.org/press-release/swri-scientists-publish-first-radiation-measurements-surface-mars",
    "data_url": "https://pds-ppi.igpp.ucla.edu/data/MSL-M-RAD-3-RDR-V1.0/",
    "notes": [
        "Historical measurement at another site; not a live value and not measured at Jezero.",
        "Surface dose rate varies inversely with atmospheric column mass (Rafkin et al. 2014, JGR Planets, "
        "doi:10.1002/2013JE004525), so it changes with season, time of day and elevation.",
        "Excludes solar energetic particle events and any suit or terrain shielding.",
    ],
}


def _clean(msg: str) -> str:
    """Error text safe to show: drop URL query strings so the API key never reaches the API response or UI."""
    msg = re.sub(r"\?[^\s'\"]*", "", str(msg))
    return re.sub(r"api_key=[^\s&'\"]+", "api_key=<hidden>", msg).split("\n")[0]


def _fetch(days: int) -> dict:
    """Fetch each DONKI list on its own: one list failing (e.g. NASA's FLR endpoint returning 404)
    must not throw away the others. Raises only if every list fails."""
    end = dt.date.today()
    start = end - dt.timedelta(days=days)
    out = {"fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "start_date": start.isoformat(), "end_date": end.isoformat(), "source": "NASA CCMC DONKI via api.nasa.gov",
           "source_url": "https://ccmc.gsfc.nasa.gov/tools/DONKI", "unavailable": {}}
    errors = []
    for kind in ("SEP", "FLR", "CME"):
        try:
            r = netutil.get(DONKI.format(kind=kind), {"startDate": start.isoformat(), "endDate": end.isoformat(),
                                                      "api_key": config.NASA_API_KEY}, timeout=40)
            data = r.json() if r.content else []
            out[kind] = data if isinstance(data, list) else []
        except Exception as e:
            out[kind] = []
            out["unavailable"][kind] = _clean(e)[:160]
            errors.append(f"{kind}: {_clean(e)}")
    if len(out["unavailable"]) == 3:
        raise RuntimeError("; ".join(errors))
    return out


def refresh(days: int = 30) -> dict:
    data = _fetch(days)
    CACHE.write_text(json.dumps(data), encoding="utf-8")
    return data


def _load_cache() -> dict | None:
    if CACHE.exists():
        try:
            return json.loads(CACHE.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def summary(days: int = 30, eva_hours: float = 4.0, allow_fetch: bool = True) -> dict:
    data, status, error = None, "unavailable", None
    cached = _load_cache()
    fresh_enough = False
    if cached:
        try:
            age_h = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(cached["fetched_at"])).total_seconds() / 3600
            fresh_enough = age_h < 3
        except Exception:
            pass
    import time
    online = netutil.is_online()
    if allow_fetch and not fresh_enough and online:
        if time.time() - _last_failure["t"] < RETRY_AFTER_S:
            error = f"last fetch failed ({_last_failure['error']}); retrying in a few minutes"
        else:
            try:
                data, status = refresh(days), "live"
            except Exception as e:  # rate limit, timeout, etc.
                msg = _clean(e)
                if "429" in msg:
                    msg = "NASA API rate limit reached (DEMO_KEY). Add your own free key from api.nasa.gov to run.bat"
                elif "403" in msg:
                    msg = "NASA API key rejected (403). Check NASA_API_KEY in run.bat"
                _last_failure.update(t=time.time(), error=msg[:160])
                error = msg[:200]
    if error is None and data is None and _last_failure["error"]:
        error = _last_failure["error"]
    if data is None and cached:
        data, status = cached, ("cached" if fresh_enough else "cached_stale")
    resp = {"status": status, "error": error, "rad_reference": RAD_REFERENCE,
            "eva_reference_dose_mSv": {
                "value": round(RAD_REFERENCE["value"] * eva_hours / 24, 3), "eva_hours": eva_hours,
                "basis": "RAD Gale 2012-13 average rate x EVA hours / 24. A REFERENCE SCALE ONLY, not a prediction: "
                         "excludes SEP events and shielding, measured at another site and time."},
            "disclaimer": "DONKI events are observed mostly from near Earth; whether an event reaches Mars depends on "
                          "planetary positions and is not modelled here. Use as an advisory to check before an EVA."}
    if data is None:
        why = (f"Could not fetch NASA DONKI: {error}." if error else
               "Offline and nothing cached yet." if not online else "Not fetched yet.")
        resp["advisory"] = {"level": "unknown", "text": f"No space-weather data available. {why} "
                                                        "Treat radiation conditions as unknown."}
        return resp

    def evt_time(e):
        return e.get("eventTime") or e.get("beginTime") or e.get("startTime") or ""

    sep = sorted(data.get("SEP", []), key=evt_time, reverse=True)
    flr = sorted(data.get("FLR", []), key=evt_time, reverse=True)
    cme = sorted(data.get("CME", []), key=evt_time, reverse=True)
    big_flares = [f for f in flr if str(f.get("classType", "")).startswith(("M", "X"))]
    now = dt.datetime.now(dt.timezone.utc)

    def within(e, days_):
        try:
            t = dt.datetime.fromisoformat(evt_time(e).replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=dt.timezone.utc)
            return (now - t).days <= days_
        except Exception:
            return False
    recent_sep = [e for e in sep if within(e, 7)]
    if recent_sep:
        adv = {"level": "caution", "text": f"{len(recent_sep)} solar energetic particle event(s) in the last 7 days of the "
                                           "DONKI catalogue. Check current conditions and shelter options before an EVA."}
    elif any(within(f, 3) and str(f.get("classType", "")).startswith("X") for f in flr):
        adv = {"level": "caution", "text": "X-class flare in the last 3 days. SEP events can follow; check before an EVA."}
    else:
        adv = {"level": "nominal", "text": "No SEP events in the last 7 days of the cached DONKI window."}
    missing = data.get("unavailable") or {}
    if missing:
        adv["text"] += (f" Not available from NASA at fetch time: {', '.join(sorted(missing))}"
                        " (that list is treated as unknown, not as zero events).")
    resp.update({
        "fetched_at": data.get("fetched_at"), "window": [data.get("start_date"), data.get("end_date")],
        "source": data.get("source"), "source_url": data.get("source_url"),
        "counts": {"SEP": None if "SEP" in missing else len(sep), "FLR": None if "FLR" in missing else len(flr),
                   "FLR_M_or_X": None if "FLR" in missing else len(big_flares),
                   "CME": None if "CME" in missing else len(cme)},
        "unavailable": missing,
        "latest": {
            "SEP": [{"time": evt_time(e), "id": e.get("sepID"), "instruments": [i.get("displayName") for i in e.get("instruments", [])],
                     "link": e.get("link")} for e in sep[:5]],
            "FLR": [{"time": evt_time(e), "class": e.get("classType"), "id": e.get("flrID"), "link": e.get("link")} for e in big_flares[:5]],
            "CME": [{"time": evt_time(e), "id": e.get("activityID"), "link": e.get("link")} for e in cme[:5]],
        },
        "advisory": adv,
    })
    return resp
