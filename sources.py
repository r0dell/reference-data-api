"""Datenquellen der Reference Data API (alle frei nutzbar).

- A19  GLEIF Global LEI Index (api.gleif.org), CC0
- A25  U.S. Treasury Fiscal Data, Treasury Reporting Rates of Exchange, public domain
- A27  U.S. Energy Information Administration (api.eia.gov), public domain, Gratis-Schluessel EIA_API_KEY
- A28  NHTSA vPIC (vpic.nhtsa.dot.gov), public domain
A23 Zeitzonen, A24 Sonne/Mond und A26 MwSt-Saetze werden lokal berechnet bzw. aus einer gepflegten Tabelle gelesen.
"""
from __future__ import annotations

import datetime as dt
import threading
import time

import httpx

UA = {"User-Agent": "ReferenceDataAPI/0.1 (contact: data-api@users.noreply.github.com)",
      "Accept": "application/vnd.api+json, application/json;q=0.9, */*;q=0.8"}
_cache: dict[str, tuple[float, object]] = {}
_lock = threading.Lock()
STATUS: dict[str, dict] = {}


class SourceUnavailable(RuntimeError):
    pass


def cached(key: str, ttl: int, loader):
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    try:
        val = loader()
        with _lock:
            _cache[key] = (now, val)
            if len(_cache) > 2000:  # Speicher begrenzen (Gratis-Server)
                for k in sorted(_cache, key=lambda k: _cache[k][0])[:500]:
                    _cache.pop(k, None)
        STATUS[key.split("|")[0]] = {"ok": True, "loaded_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        return val
    except Exception as e:  # alte Daten weiterverwenden, falls vorhanden
        STATUS[key.split("|")[0]] = {"ok": False, "error": str(e)[:200],
                                     "at": dt.datetime.now(dt.timezone.utc).isoformat()}
        if hit:
            return hit[1]
        raise SourceUnavailable(f"Data source temporarily unavailable ({key.split('|')[0]}). Please retry later.")


def get_json(url: str, params: dict | None = None, timeout: float = 25, allow_404: bool = False):
    r = httpx.get(url, params=params, headers=UA, timeout=timeout, follow_redirects=True)
    if allow_404 and r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


GLEIF = "https://api.gleif.org/api/v1"
FISCAL = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/rates_of_exchange"
EIA = "https://api.eia.gov/v2/seriesid/{sid}"
VPIC = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}"


def _k(name, params):
    return name + "|" + "&".join(f"{k}={v}" for k, v in sorted((params or {}).items()))


def gleif(path: str, params: dict | None = None, allow_404: bool = False):
    return cached(_k("gleif" + path, params), 6 * 3600,
                  lambda: get_json(GLEIF + path, params, allow_404=allow_404) or {"data": None})


def fiscal(params: dict):
    return cached(_k("treasury", params), 6 * 3600, lambda: get_json(FISCAL, params))


def eia_series(sid: str, api_key: str, length: int):
    return cached(_k("eia", {"sid": sid, "n": length}), 1800,
                  lambda: get_json(EIA.format(sid=sid), {"api_key": api_key, "length": length}))


def vpic(vin: str, year: str | None):
    p = {"format": "json", **({"modelyear": year} if year else {})}
    return cached(_k("vpic", {"vin": vin, **p}), 7 * 86400, lambda: get_json(VPIC.format(vin=vin), p))
