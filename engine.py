"""Rechenkern der Reference Data API.

A19  LEI-Firmenprüfung (GLEIF)                 /v1/lei
A23  Zeitzonen-Rechner (IANA, lokal)           /v1/timezone, /v1/meeting-window
A24  Sonnen- & Mondzeiten (lokal berechnet)     /v1/sun-moon
A25  US-Treasury-Buchungskurse (Fiscal Data)   /v1/treasury-rate
A26  EU-Mehrwertsteuersätze (gepflegt)          /v1/vat
A27  Energie-Lagerdaten & EIA-Kalender         /v1/energy-calendar, /v1/energy-stocks
A28  VIN-Decoder (NHTSA vPIC)                  /v1/vin
"""
from __future__ import annotations

import datetime as dt
import os
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

import sources as src
import vat as V

UTC = dt.timezone.utc


def _today() -> dt.date:
    return dt.datetime.now(UTC).date()


def _date(s: str | None, name: str = "date") -> dt.date:
    if not s:
        return _today()
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        raise ValueError(f"{name} must be YYYY-MM-DD")


# ================================================================== A19 LEI
LEI_RE = re.compile(r"^[A-Z0-9]{18}[0-9]{2}$")
ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


def lei_checksum_ok(lei: str) -> bool:
    digits = "".join(str(int(ch, 36)) for ch in lei)
    return int(digits) % 97 == 1


def _addr(a: dict | None) -> dict | None:
    if not a:
        return None
    return {"lines": a.get("addressLines"), "city": a.get("city"), "region": a.get("region"),
            "country": a.get("country"), "postal_code": a.get("postalCode")}


def _entity(rec: dict) -> dict:
    at = rec.get("attributes", {})
    en, rg = at.get("entity", {}), at.get("registration", {})
    return {
        "lei": at.get("lei"), "legal_name": (en.get("legalName") or {}).get("name"),
        "other_names": [n.get("name") for n in en.get("otherNames") or [] if n.get("name")][:5],
        "status": en.get("status"), "jurisdiction": en.get("jurisdiction"),
        "legal_form_code": (en.get("legalForm") or {}).get("id"), "category": en.get("category"),
        "legal_address": _addr(en.get("legalAddress")), "headquarters": _addr(en.get("headquartersAddress")),
        "registered_at": (en.get("registeredAt") or {}).get("id"),
        "registered_as": en.get("registeredAs"),
        "lei_registration_status": rg.get("status"), "initial_registration": rg.get("initialRegistrationDate"),
        "last_update": rg.get("lastUpdateDate"), "next_renewal": rg.get("nextRenewalDate"),
        "lei_lapsed": rg.get("status") == "LAPSED",
    }


def _parent(lei: str, kind: str) -> dict | None:
    d = src.gleif(f"/lei-records/{lei}/{kind}", allow_404=True).get("data")
    if not d:
        return None
    a = d.get("attributes", {})
    return {"lei": a.get("lei"), "legal_name": ((a.get("entity") or {}).get("legalName") or {}).get("name"),
            "country": ((a.get("entity") or {}).get("legalAddress") or {}).get("country")}


def lei_lookup(lei: str | None = None, name: str | None = None, isin: str | None = None,
               include_related: bool = True) -> dict:
    if sum(bool(x) for x in (lei, name, isin)) != 1:
        raise ValueError("Give exactly one of lei, name or isin")
    if lei:
        lei = lei.strip().upper()
        if not LEI_RE.match(lei) or not lei_checksum_ok(lei):
            raise ValueError("Not a valid LEI (20 characters, ISO 17442 check digits)")
        rec = src.gleif(f"/lei-records/{lei}", allow_404=True).get("data")
        if not rec:
            raise KeyError(f"LEI {lei} not found in the GLEIF index")
        recs = [rec]
    else:
        if isin:
            isin = isin.strip().upper()
            if not ISIN_RE.match(isin):
                raise ValueError("Not a valid ISIN (12 characters, e.g. US0378331005)")
            params = {"filter[isin]": isin, "page[size]": 5}
        else:
            if len(name.strip()) < 2:
                raise ValueError("name is too short")
            params = {"filter[fulltext]": name.strip(), "page[size]": 10}
        recs = src.gleif("/lei-records", params).get("data") or []
        if not recs:
            raise KeyError(f"No legal entity found for {'ISIN ' + isin if isin else repr(name)}")
    out = [_entity(r) for r in recs]
    if include_related and len(out) == 1:
        e = out[0]
        e["direct_parent"] = _parent(e["lei"], "direct-parent")
        e["ultimate_parent"] = _parent(e["lei"], "ultimate-parent")
        ch = src.gleif(f"/lei-records/{e['lei']}/direct-children", {"page[size]": 1}, allow_404=True)
        e["direct_children_count"] = (((ch.get("meta") or {}).get("pagination") or {}).get("total") or 0)
        isins = src.gleif(f"/lei-records/{e['lei']}/isins", {"page[size]": 20}, allow_404=True)
        e["isins"] = [i.get("attributes", {}).get("isin") for i in isins.get("data") or []]
        e["isins_total"] = (((isins.get("meta") or {}).get("pagination") or {}).get("total") or len(e["isins"]))
    return {"query": {"lei": lei, "name": name, "isin": isin}, "matches": len(out), "entities": out,
            "source": "GLEIF Global LEI Index (api.gleif.org), CC0"}


# ================================================================== A23 Zeitzonen
ALIASES = {"UTC": "UTC", "GMT": "UTC", "CET": "Europe/Berlin", "ET": "America/New_York", "EST": "America/New_York",
           "CT": "America/Chicago", "PT": "America/Los_Angeles", "JST": "Asia/Tokyo", "ZURICH": "Europe/Zurich",
           "NEW YORK": "America/New_York", "LONDON": "Europe/London", "TOKYO": "Asia/Tokyo",
           "SINGAPORE": "Asia/Singapore", "HONG KONG": "Asia/Hong_Kong", "SYDNEY": "Australia/Sydney",
           "CHICAGO": "America/Chicago", "FRANKFURT": "Europe/Berlin", "PARIS": "Europe/Paris"}


def _zone(name: str) -> ZoneInfo:
    n = (name or "").strip()
    n = ALIASES.get(n.upper(), n)
    try:
        return ZoneInfo(n)
    except (ZoneInfoNotFoundError, ValueError):
        low = {z.lower(): z for z in available_timezones()}
        hit = low.get(n.lower()) or next((z for l, z in low.items() if l.endswith("/" + n.lower().replace(" ", "_"))), None)
        if hit:
            return ZoneInfo(hit)
        raise KeyError(f"Unknown time zone '{name}'. Use an IANA name like Europe/Zurich or America/New_York")


def _parse_dt(s: str | None, tz: ZoneInfo) -> dt.datetime:
    if not s:
        return dt.datetime.now(UTC).astimezone(tz)
    try:
        t = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("time must be ISO 8601, e.g. 2026-11-01T15:30 or 2026-11-01T15:30:00Z")
    return t.replace(tzinfo=tz) if t.tzinfo is None else t.astimezone(tz)


def _next_transition(tz: ZoneInfo, start: dt.datetime, days: int = 400) -> dict | None:
    u0 = start.astimezone(UTC)
    off0 = start.utcoffset()
    step = dt.timedelta(hours=6)
    t = u0
    for _ in range(days * 4):
        nt = t + step
        if nt.astimezone(tz).utcoffset() != off0:
            lo, hi = t, nt
            while hi - lo > dt.timedelta(minutes=1):
                mid = lo + (hi - lo) / 2
                if mid.astimezone(tz).utcoffset() == off0:
                    lo = mid
                else:
                    hi = mid
            hi = hi.replace(second=0, microsecond=0)
            after = hi.astimezone(tz)
            return {"at_utc": hi.isoformat(), "local_after": after.isoformat(),
                    "offset_before": _fmt_off(off0), "offset_after": _fmt_off(after.utcoffset()),
                    "dst_after": bool(after.dst())}
        t = nt
    return None


def _fmt_off(o: dt.timedelta) -> str:
    m = int(o.total_seconds() // 60)
    return f"{'+' if m >= 0 else '-'}{abs(m) // 60:02d}:{abs(m) % 60:02d}"


def timezone_info(zone: str, time: str | None = None, to: str | None = None) -> dict:
    tz = _zone(zone)
    t = _parse_dt(time, tz)
    res = {"zone": tz.key, "local_time": t.isoformat(timespec="seconds"), "utc_time": t.astimezone(UTC).isoformat(timespec="seconds"),
           "utc_offset": _fmt_off(t.utcoffset()), "abbreviation": t.tzname(), "dst_active": bool(t.dst()),
           "next_transition": _next_transition(tz, t)}
    if to:
        tz2 = _zone(to)
        t2 = t.astimezone(tz2)
        res["converted"] = {"zone": tz2.key, "local_time": t2.isoformat(timespec="seconds"),
                            "utc_offset": _fmt_off(t2.utcoffset()), "abbreviation": t2.tzname(),
                            "difference_hours": (t2.utcoffset() - t.utcoffset()).total_seconds() / 3600}
    return res


def meeting_window(zones: str, date: str | None = None, start_hour: int = 9, end_hour: int = 17) -> dict:
    names = [z for z in (zones or "").split(",") if z.strip()]
    if not 2 <= len(names) <= 10:
        raise ValueError("Give 2 to 10 comma-separated zones")
    if not (0 <= start_hour < end_hour <= 24):
        raise ValueError("start_hour must be before end_hour (0-24)")
    d = _date(date)
    tzs = [_zone(n) for n in names]
    windows = []
    for tz in tzs:
        s = dt.datetime.combine(d, dt.time(start_hour), tz)
        e = dt.datetime.combine(d, dt.time(0), tz) + dt.timedelta(hours=end_hour)
        windows.append((s.astimezone(UTC), e.astimezone(UTC)))
    lo, hi = max(w[0] for w in windows), min(w[1] for w in windows)
    overlap = None
    if lo < hi:
        overlap = {"start_utc": lo.isoformat(), "end_utc": hi.isoformat(),
                   "minutes": int((hi - lo).total_seconds() // 60),
                   "local": [{"zone": tz.key, "start": lo.astimezone(tz).strftime("%Y-%m-%d %H:%M"),
                              "end": hi.astimezone(tz).strftime("%Y-%m-%d %H:%M")} for tz in tzs]}
    return {"date": d.isoformat(), "working_hours": f"{start_hour:02d}:00-{end_hour:02d}:00 local",
            "zones": [t.key for t in tzs], "overlap": overlap,
            "note": None if overlap else "No common working-hours window on this date"}


# ================================================================== A24 Sonne & Mond
MOON_PHASES = [(1.0, "New Moon"), (6.4, "Waxing Crescent"), (8.4, "First Quarter"), (13.8, "Waxing Gibbous"),
               (15.8, "Full Moon"), (21.1, "Waning Gibbous"), (23.1, "Last Quarter"), (27.7, "Waning Crescent"),
               (28.1, "New Moon")]


def sun_moon(lat: float, lon: float, date: str | None = None, zone: str | None = None) -> dict:
    from astral import Observer, moon
    from astral import sun as S
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("lat must be -90..90 and lon -180..180")
    d = _date(date)
    tz = _zone(zone) if zone else UTC
    obs = Observer(latitude=lat, longitude=lon)

    def at(fn, *a):
        try:
            return fn(obs, d, *a, tzinfo=tz).isoformat(timespec="seconds")
        except ValueError:
            return None

    sunrise, sunset = at(S.sunrise), at(S.sunset)
    elev_noon = S.elevation(obs, S.noon(obs, d, tzinfo=tz))
    if sunrise and sunset:
        day_len = (dt.datetime.fromisoformat(sunset) - dt.datetime.fromisoformat(sunrise)).total_seconds()
        polar = None
    else:
        day_len = 86400.0 if elev_noon > 0 else 0.0
        polar = "polar day (sun does not set)" if elev_noon > 0 else "polar night (sun does not rise)"
    ph = moon.phase(d)
    name = next(n for lim, n in MOON_PHASES if ph < lim)
    illum = round((1 - __import__("math").cos(2 * __import__("math").pi * ph / 29.530588)) / 2 * 100, 1)
    return {"lat": lat, "lon": lon, "date": d.isoformat(), "zone": getattr(tz, "key", "UTC"),
            "sun": {"dawn_civil": at(S.dawn), "sunrise": sunrise, "solar_noon": S.noon(obs, d, tzinfo=tz).isoformat(timespec="seconds"),
                    "sunset": sunset, "dusk_civil": at(S.dusk), "day_length_hours": round(day_len / 3600, 3),
                    "max_elevation_deg": round(elev_noon, 2), "polar": polar},
            "moon": {"phase": name, "phase_day": round(ph, 2), "illumination_pct": illum,
                     "moonrise": at(moon.moonrise), "moonset": at(moon.moonset)},
            "method": "Computed (NOAA solar equations via astral); accuracy about 1 minute, refraction included"}


# ================================================================== A25 Treasury-Buchungskurse
ISO_COUNTRY = {"EUR": "Euro Zone", "CHF": "Switzerland", "GBP": "United Kingdom", "JPY": "Japan", "CAD": "Canada",
               "CNY": "China", "AUD": "Australia", "MXN": "Mexico", "INR": "India", "SEK": "Sweden",
               "NOK": "Norway", "DKK": "Denmark", "BRL": "Brazil", "KRW": "Korea", "HKD": "Hong Kong",
               "SGD": "Singapore", "ZAR": "South Africa", "PLN": "Poland", "CZK": "Czech Republic",
               "HUF": "Hungary", "TRY": "Turkey", "ILS": "Israel", "NZD": "New Zealand", "THB": "Thailand",
               "TWD": "Taiwan", "PHP": "Philippines", "IDR": "Indonesia", "MYR": "Malaysia", "SAR": "Saudi Arabia",
               "AED": "United Arab Emirates", "ARS": "Argentina", "CLP": "Chile", "COP": "Colombia", "PEN": "Peru",
               "EGP": "Egypt", "NGN": "Nigeria", "PKR": "Pakistan", "VND": "Vietnam", "RON": "Romania",
               "ISK": "Iceland", "KWD": "Kuwait", "QAR": "Qatar"}


def treasury_rate(currency: str, date: str | None = None, amount: float | None = None) -> dict:
    q = (currency or "").strip()
    if not q:
        raise ValueError("currency is required (ISO code like EUR or a country name)")
    d = _date(date)
    country = ISO_COUNTRY.get(q.upper(), q)
    data = src.fiscal({"filter": f"record_date:lte:{d.isoformat()}", "sort": "-record_date", "page[size]": 600})
    rows = data.get("data") or []
    if not rows:
        raise KeyError("No Treasury reporting rates available for that date")
    latest = rows[0]["record_date"]
    cur = [r for r in rows if r["record_date"] == latest]
    lo = country.lower()
    hits = [r for r in cur if r["country"].lower() == lo] or \
           [r for r in cur if lo in r["country_currency_desc"].lower()]
    if not hits:
        raise KeyError(f"No Treasury rate for '{currency}' in the {latest} table")
    out = []
    for r in hits:
        rate = float(r["exchange_rate"])
        item = {"country_currency": r["country_currency_desc"], "foreign_per_usd": rate,
                "usd_per_foreign": round(1 / rate, 8) if rate else None, "effective_date": r["effective_date"]}
        if amount is not None:
            item["amount_foreign"] = amount
            item["amount_usd"] = round(amount / rate, 2) if rate else None
        out.append(item)
    return {"requested_date": d.isoformat(), "table_date": latest, "rates": out,
            "note": "Official quarterly Treasury Reporting Rates of Exchange, used by US federal agencies; "
                    "amendments are published when a currency moves 10% or more.",
            "source": "U.S. Treasury, Bureau of the Fiscal Service (fiscaldata.treasury.gov), public domain"}


# ================================================================== A26 MwSt
def vat_rates(country: str | None = None, amount: float | None = None, rate: str = "standard",
              amount_includes_vat: bool = False) -> dict:
    def row(code):
        n, std, red, sup, park, cur = V.RATES[code]
        return {"country_code": code, "country": n, "standard": std, "reduced": red, "super_reduced": sup,
                "parking": park, "currency": cur}
    base = {"verified": V.VERIFIED, "changes_since_2025": V.CHANGES,
            "note": "Product-level assignment of reduced rates varies; check the EU TEDB database for a "
                    "specific good or service.", "source": "Maintained table, checked against national tax "
                                                           "authorities and EU overviews"}
    if not country:
        return {**base, "countries": [row(c) for c in sorted(V.RATES)]}
    code = country.strip().upper()
    code = V.ALIASES.get(code, code)
    if code is None:
        raise KeyError("The United Kingdom is not in the EU VAT area")
    if code not in V.RATES:
        code = next((c for c, r in V.RATES.items() if r[0].lower() == country.strip().lower()), None)
        if not code:
            raise KeyError(f"Unknown EU country '{country}'. Use a code like DE, FR, IT or EL (Greece)")
    r = row(code)
    res = {**base, **r, "changes_since_2025": [c for c in V.CHANGES if c["country"] == code]}
    if amount is not None:
        if rate == "standard":
            pct = r["standard"]
        else:
            try:
                pct = float(rate)
            except ValueError:
                raise ValueError("rate must be 'standard' or a number like 7")
            valid = [r["standard"], *r["reduced"], r["super_reduced"], r["parking"], 0]
            if pct not in [v for v in valid if v is not None]:
                raise ValueError(f"{pct}% is not a VAT rate in {r['country']}")
        if amount_includes_vat:
            net = amount / (1 + pct / 100)
            gross = amount
        else:
            net, gross = amount, amount * (1 + pct / 100)
        res["calculation"] = {"rate_pct": pct, "net": round(net, 2), "vat": round(gross - net, 2),
                              "gross": round(gross, 2), "currency": r["currency"]}
    return res


# ================================================================== A27 Energie
def _nth_weekday(y, m, wd, n):
    d = dt.date(y, m, 1)
    d += dt.timedelta(days=(wd - d.weekday()) % 7)
    return d + dt.timedelta(weeks=n - 1)


def _last_weekday(y, m, wd):
    d = dt.date(y, m + 1, 1) - dt.timedelta(days=1) if m < 12 else dt.date(y, 12, 31)
    return d - dt.timedelta(days=(d.weekday() - wd) % 7)


def us_federal_holidays(y: int) -> dict[dt.date, str]:
    def obs(d):
        return d - dt.timedelta(days=1) if d.weekday() == 5 else d + dt.timedelta(days=1) if d.weekday() == 6 else d
    h = {obs(dt.date(y, 1, 1)): "New Year's Day", _nth_weekday(y, 1, 0, 3): "Martin Luther King Jr. Day",
         _nth_weekday(y, 2, 0, 3): "Presidents' Day", _last_weekday(y, 5, 0): "Memorial Day",
         obs(dt.date(y, 6, 19)): "Juneteenth", obs(dt.date(y, 7, 4)): "Independence Day",
         _nth_weekday(y, 9, 0, 1): "Labor Day", _nth_weekday(y, 10, 0, 2): "Columbus Day",
         obs(dt.date(y, 11, 11)): "Veterans Day", _nth_weekday(y, 11, 3, 4): "Thanksgiving",
         obs(dt.date(y, 12, 25)): "Christmas Day"}
    nxt = dt.date(y + 1, 1, 1)
    if nxt.weekday() == 5:
        h[dt.date(y, 12, 31)] = "New Year's Day (observed)"
    return h


REPORTS = {
    "petroleum": {"name": "Weekly Petroleum Status Report (crude oil, gasoline, distillate stocks)",
                  "weekday": 2, "time": "10:30", "delayed_time": "11:00"},
    "natural-gas": {"name": "Weekly Natural Gas Storage Report", "weekday": 3, "time": "10:30",
                    "delayed_time": "10:30"},
}


def _release(kind: str, week_monday: dt.date) -> dict:
    r = REPORTS[kind]
    hol = {}
    for y in {week_monday.year, (week_monday + dt.timedelta(days=6)).year}:
        hol.update(us_federal_holidays(y))
    day = week_monday + dt.timedelta(days=r["weekday"])
    if kind == "natural-gas":  # nur ein Feiertag am Donnerstag selbst verschiebt (auf Mi 12:00)
        hit = [day] if day in hol else []
    else:  # Feiertag Mo-Mi: Petroleum-Bericht einen Tag später um 11:00
        hit = [d for d in hol if week_monday <= d <= day]
    t, shifted = r["time"], None
    if hit:
        if kind == "natural-gas":
            day -= dt.timedelta(days=1)
            t = "12:00"
        else:
            day += dt.timedelta(days=1)
            t = r["delayed_time"]
        shifted = f"shifted for {', '.join(hol[d] for d in sorted(hit))}"
    et = dt.datetime.combine(day, dt.time(*map(int, t.split(":"))), ZoneInfo("America/New_York"))
    return {"report": kind, "name": r["name"], "release_et": et.isoformat(), "release_utc": et.astimezone(UTC).isoformat(),
            "rule_based": True, "shift": shifted}


def energy_calendar(weeks: int = 4, date: str | None = None) -> dict:
    if not 1 <= weeks <= 26:
        raise ValueError("weeks must be 1..26")
    d = _date(date)
    monday = d - dt.timedelta(days=d.weekday())
    now = dt.datetime.now(UTC)
    out = []
    for w in range(weeks + 1):
        for k in REPORTS:
            ev = _release(k, monday + dt.timedelta(weeks=w))
            if dt.datetime.fromisoformat(ev["release_utc"]).date() >= d:
                out.append(ev)
    out.sort(key=lambda e: e["release_utc"])
    out = out[: weeks * 2]
    upcoming = [e for e in out if dt.datetime.fromisoformat(e["release_utc"]) > now]
    return {"from": d.isoformat(), "releases": out, "next": upcoming[0] if upcoming else None,
            "note": "Times follow EIA's regular schedule and US federal holidays. EIA occasionally announces "
                    "other changes; such exceptions are not covered.",
            "source": "U.S. Energy Information Administration release schedule rules"}


SERIES = {"crude_ex_spr_kbbl": "PET.WCESTUS1.W", "crude_spr_kbbl": "PET.WCSSTUS1.W",
          "gasoline_kbbl": "PET.WGTSTUS1.W", "distillate_kbbl": "PET.WDISTUS1.W",
          "cushing_crude_kbbl": "PET.W_EPC0_SAX_YCUOK_MBBL.W", "natgas_storage_bcf": "NG.NW2_EPG0_SWO_R48_BCF.W"}


def energy_stocks(weeks: int = 2) -> dict:
    key = os.environ.get("EIA_API_KEY", "").strip()
    if not key:
        raise src.SourceUnavailable("EIA stock data is not configured on this server yet (EIA_API_KEY missing)")
    if not 2 <= weeks <= 52:
        raise ValueError("weeks must be 2..52")
    out = {}
    for name, sid in SERIES.items():
        data = src.eia_series(sid, key, weeks)
        pts = sorted(((p["period"], p["value"]) for p in (data.get("response") or {}).get("data", [])
                      if p.get("value") is not None), reverse=True)
        if not pts:
            continue
        latest, prev = pts[0], (pts[1] if len(pts) > 1 else None)
        out[name] = {"week_ending": latest[0], "value": float(latest[1]),
                     "change_vs_prior_week": round(float(latest[1]) - float(prev[1]), 3) if prev else None,
                     "history": [{"week_ending": p, "value": float(v)} for p, v in pts]}
    if not out:
        raise src.SourceUnavailable("EIA returned no data")
    return {"stocks": out, "units": {"kbbl": "thousand barrels", "bcf": "billion cubic feet"},
            "source": "U.S. Energy Information Administration (api.eia.gov), public domain"}


# ================================================================== A28 VIN
VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")
_TRANS = {**{str(i): i for i in range(10)}, **dict(zip("ABCDEFGH", range(1, 9))), **dict(zip("JKLMN", range(1, 6))),
          "P": 7, "R": 9, **dict(zip("STUVWXYZ", range(2, 10)))}
_WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]


def vin_check_digit(vin: str) -> str:
    s = sum(_TRANS[c] * w for c, w in zip(vin, _WEIGHTS)) % 11
    return "X" if s == 10 else str(s)


VIN_FIELDS = {"Make": "make", "Model": "model", "ModelYear": "model_year", "Trim": "trim", "Series": "series",
              "BodyClass": "body_class", "VehicleType": "vehicle_type", "Doors": "doors", "DriveType": "drive_type",
              "EngineCylinders": "engine_cylinders", "DisplacementL": "displacement_l", "EngineHP": "engine_hp",
              "FuelTypePrimary": "fuel_type", "ElectrificationLevel": "electrification",
              "TransmissionStyle": "transmission", "GVWR": "gvwr_class", "Manufacturer": "manufacturer",
              "PlantCity": "plant_city", "PlantState": "plant_state", "PlantCountry": "plant_country"}


def vin_decode(vin: str, model_year: int | None = None) -> dict:
    v = (vin or "").strip().upper()
    if not VIN_RE.match(v):
        raise ValueError("VIN must be 17 characters (letters I, O and Q are not used)")
    if model_year is not None and not 1980 <= int(model_year) <= _today().year + 2:
        raise ValueError("model_year out of range")
    r = (src.vpic(v, str(model_year) if model_year else None).get("Results") or [{}])[0]
    out = {}
    for k, name in VIN_FIELDS.items():
        val = r.get(k)
        if val not in (None, "", "Not Applicable"):
            if name == "displacement_l":
                try:
                    val = round(float(val), 2)
                except ValueError:
                    pass
            out[name] = val
    codes = [c.strip() for c in str(r.get("ErrorCode", "")).split(",") if c.strip()]
    cd = vin_check_digit(v)
    return {"vin": v, "decoded": out, "check_digit_valid": cd == v[8], "expected_check_digit": cd,
            "decode_ok": codes in ([], ["0"]), "nhtsa_message": r.get("ErrorText") or None,
            "note": "The check digit rule applies to North American VINs; other markets may not use it.",
            "source": "NHTSA vPIC (vpic.nhtsa.dot.gov), public domain"}
