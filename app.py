"""HTTP-API: Reference Data API (LEI, Zeitzonen, Sonne/Mond, Treasury-Kurse, EU-MwSt, EIA, VIN)."""
from typing import Optional

from fastapi import FastAPI, HTTPException, Query

import engine as e
import sources as src
import vat

app = FastAPI(
    title="Reference Data API",
    version="0.1.0",
    description=("Reference lookups for agents: legal entity identifiers (GLEIF) with parents and ISINs, time zones "
                 "and meeting windows, sunrise/sunset and moon phase, official US Treasury reporting exchange rates, "
                 "EU VAT rates with net/gross calculation, EIA energy report calendar and weekly stocks, and VIN "
                 "decoding (NHTSA). Every response names its source."),
)


def _run(fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except KeyError as ex:
        raise HTTPException(status_code=404, detail=str(ex).strip("'\""))
    except src.SourceUnavailable as ex:
        raise HTTPException(status_code=503, detail=str(ex))
    except ValueError as ex:
        raise HTTPException(status_code=400, detail=str(ex))


@app.get("/v1/lei", summary="A19: Look up a legal entity by LEI, name or ISIN (with parents and ISINs)")
def lei(lei: Optional[str] = Query(None, examples=["HWUPKR0MPOU8FGXBT394"]),
        name: Optional[str] = Query(None, examples=["Nestle S.A."]),
        isin: Optional[str] = Query(None, examples=["US0378331005"])):
    return _run(e.lei_lookup, lei, name, isin)


@app.get("/v1/timezone", summary="A23: Local time, UTC offset, next DST change; optional conversion")
def timezone(zone: str = Query(..., examples=["Europe/Zurich"]),
             time: Optional[str] = Query(None, examples=["2026-11-01T15:30"]),
             to: Optional[str] = Query(None, examples=["America/New_York"])):
    return _run(e.timezone_info, zone, time, to)


@app.get("/v1/meeting-window", summary="A23: Common working-hours window across time zones")
def meeting(zones: str = Query(..., examples=["Europe/Zurich,America/New_York,Asia/Tokyo"]),
            date: Optional[str] = None, start_hour: int = 9, end_hour: int = 17):
    return _run(e.meeting_window, zones, date, start_hour, end_hour)


@app.get("/v1/sun-moon", summary="A24: Sunrise, sunset, twilight, day length and moon phase")
def sun_moon(lat: float = Query(..., examples=[47.37]), lon: float = Query(..., examples=[8.54]),
             date: Optional[str] = None, zone: Optional[str] = Query(None, examples=["Europe/Zurich"])):
    return _run(e.sun_moon, lat, lon, date, zone)


@app.get("/v1/treasury-rate", summary="A25: Official US Treasury reporting rate of exchange")
def treasury_rate(currency: str = Query(..., examples=["EUR"]), date: Optional[str] = None,
                  amount: Optional[float] = None):
    return _run(e.treasury_rate, currency, date, amount)


@app.get("/v1/vat", summary="A26: EU VAT rates for a country (or all) with optional net/gross calculation")
def vat_rates(country: Optional[str] = Query(None, examples=["DE"]), amount: Optional[float] = None,
              rate: str = "standard", amount_includes_vat: bool = False):
    return _run(e.vat_rates, country, amount, rate, amount_includes_vat)


@app.get("/v1/energy-calendar", summary="A27: Upcoming EIA petroleum and natural-gas storage report times")
def energy_calendar(weeks: int = 4, date: Optional[str] = None):
    return _run(e.energy_calendar, weeks, date)


@app.get("/v1/energy-stocks", summary="A27: Latest weekly US crude, gasoline, distillate and gas storage")
def energy_stocks(weeks: int = 2):
    return _run(e.energy_stocks, weeks)


@app.get("/v1/vin", summary="A28: Decode a vehicle identification number")
def vin(vin: str = Query(..., examples=["1HGCM82633A004352"]), model_year: Optional[int] = None):
    return _run(e.vin_decode, vin, model_year)


@app.get("/v1/sources", summary="Data source status (free)")
def sources():
    import os
    return {"status": src.STATUS, "vat_table_verified": vat.VERIFIED,
            "eia_configured": bool(os.environ.get("EIA_API_KEY"))}


@app.get("/health", include_in_schema=False)
def health():
    return {"ok": True}
