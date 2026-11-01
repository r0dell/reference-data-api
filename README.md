# Reference Data API (v0.1)

Nachschlage-Daten für KI-Agenten, bezahlt pro Abfrage über x402 (USDC auf Base).

| Agent | Endpunkt | Liefert | Preis |
|---|---|---|---|
| A19 | `/v1/lei?lei=` / `?name=` / `?isin=` | Firma nach LEI, Name oder ISIN: Status, Sitz, Mutter, Töchter, ISINs (GLEIF) | 0.012 USDC |
| A23 | `/v1/timezone?zone=Europe/Zurich&to=America/New_York`, `/v1/meeting-window?zones=..` | Ortszeit, Offset, nächste Zeitumstellung, Umrechnung, gemeinsames Meeting-Fenster | 0.013 USDC |
| A24 | `/v1/sun-moon?lat=47.37&lon=8.54` | Sonnenauf-/-untergang, Dämmerung, Tageslänge, Mondphase | 0.014 USDC |
| A25 | `/v1/treasury-rate?currency=EUR&amount=1000` | Offizielle US-Treasury-Buchungskurse (quartalsweise) | 0.015 USDC |
| A26 | `/v1/vat?country=DE&amount=100` | EU-MwSt-Sätze aller 27 Staaten, Netto/Brutto-Rechnung, Änderungen seit 2025 | 0.016 USDC |
| A27 | `/v1/energy-calendar`, `/v1/energy-stocks` | EIA-Berichtstermine (feiertagsbereinigt) und wöchentliche Lagerdaten | 0.017 USDC |
| A28 | `/v1/vin?vin=1HGCM82633A004352` | VIN entschlüsseln (NHTSA) mit Prüfziffer-Check | 0.018 USDC |
| – | `/v1/sources`, `/docs`, `/health` | Quellenstatus, Doku | gratis |

Quellen: GLEIF (CC0), U.S. Treasury Fiscal Data, EIA, NHTSA vPIC (alle public domain);
Zeitzonen (IANA tzdata) und Sonne/Mond (astral) werden lokal berechnet; MwSt-Tabelle gepflegt in `vat.py` (Stand siehe `VERIFIED`).
`/v1/energy-stocks` braucht den Gratis-Schlüssel `EIA_API_KEY` (eia.gov/opendata), sonst 503.

Tests: `python -m pytest -q`
