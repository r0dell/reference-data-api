"""Reference Data API mit x402-Bezahlung (USDC auf Base).

Umgebungsvariablen:
  PAY_TO              Wallet-Adresse des Bündels (0x...), hierhin gehen die Zahlungen. Pflicht.
  X402_NETWORK        "testnet" (Base Sepolia, Standard) oder "mainnet" (Base).
  CDP_API_KEY_ID      Coinbase-Developer-Platform-Key. Für mainnet und Bazaar-Listing nötig.
  CDP_API_KEY_SECRET  dazugehöriges Secret.

Gratis:  /v1/sources, /health, /docs
Bezahlt: A19 /v1/lei · A23 /v1/timezone, /v1/meeting-window · A24 /v1/sun-moon · A25 /v1/treasury-rate
         A26 /v1/vat · A28 /v1/vin · A30 /v1/iban, /v1/bic · A36 /v1/country, /v1/currency
         (A27 EIA am 1.11.2026 gelöscht)
Jeder Agent hat einen eigenen Preis; daran erkennt der Einnahmen-Monitor, wer verkauft hat.
"""
import os
import re

from x402 import x402ResourceServer
from x402.extensions.bazaar import (
    OutputConfig,
    bazaar_resource_server_extension,
    declare_discovery_extension,
)
from x402.http import FacilitatorConfig, HTTPFacilitatorClient
from x402.http.middleware.fastapi import PaymentMiddlewareASGI
from x402.http.types import PaymentOption, RouteConfig
from x402.mechanisms.evm.exact import ExactEvmServerScheme

from app import app

NETWORKS = {"testnet": "eip155:84532", "mainnet": "eip155:8453"}
TESTNET_FACILITATOR = os.environ.get("FACILITATOR_URL", "https://x402.org/facilitator")

PAY_TO = os.environ.get("PAY_TO", "").strip()
if not re.fullmatch(r"0x[0-9a-fA-F]{40}", PAY_TO):
    raise SystemExit("PAY_TO fehlt oder ist keine gültige Wallet-Adresse (0x + 40 Hex-Zeichen).")

MODE = os.environ.get("X402_NETWORK", "testnet").lower()
if MODE not in NETWORKS:
    raise SystemExit("X402_NETWORK muss 'testnet' oder 'mainnet' sein.")
NETWORK = NETWORKS[MODE]

CDP_ID = os.environ.get("CDP_API_KEY_ID", "").strip().strip('"\'').strip()
CDP_SECRET = os.environ.get("CDP_API_KEY_SECRET", "").strip().strip('"\'').strip()
if "BEGIN" in CDP_SECRET:
    CDP_SECRET = CDP_SECRET.replace("\\n", "\n")  # PEM aus einzeiligem Feld


def _describe_cdp_keys() -> str:
    """Format der Keys beschreiben, ohne Werte preiszugeben."""
    id_kind = ("uuid" if re.fullmatch(r"[0-9a-fA-F-]{36}", CDP_ID)
               else "organizations-path" if CDP_ID.startswith("organizations/") else "other")
    if "BEGIN EC PRIVATE KEY" in CDP_SECRET:
        sec_kind = "ec-pem"
    else:
        try:
            import base64
            sec_kind = f"base64-{len(base64.b64decode(CDP_SECRET, validate=True))}bytes"
        except Exception:
            sec_kind = "unparseable"
    return f"CDP key: id={id_kind} (len {len(CDP_ID)}), secret={sec_kind} (len {len(CDP_SECRET)})"


if CDP_ID and CDP_SECRET:
    from cdp.x402 import create_facilitator_config
    print(_describe_cdp_keys(), flush=True)
    facilitator_cfg = create_facilitator_config(CDP_ID, CDP_SECRET)
elif MODE == "mainnet":
    raise SystemExit("Für mainnet werden CDP_API_KEY_ID und CDP_API_KEY_SECRET benötigt.")
else:
    facilitator_cfg = FacilitatorConfig(url=TESTNET_FACILITATOR)

server = x402ResourceServer(HTTPFacilitatorClient(facilitator_cfg))
server.register(NETWORK, ExactEvmServerScheme())
server.register_extension(bazaar_resource_server_extension)

SVC = "Reference Data API"


def pay(price: str) -> PaymentOption:
    return PaymentOption(scheme="exact", pay_to=PAY_TO, price=price, network=NETWORK)


def route(price, desc, tags, inp, schema, required, example):
    return RouteConfig(
        accepts=pay(price), description=desc, mime_type="application/json", service_name=SVC, tags=tags,
        extensions=declare_discovery_extension(
            input=inp, input_schema={"properties": schema, "required": required},
            output=OutputConfig(example=example)))


S = lambda d: {"type": "string", "description": d}

# Preise (je Agent verschieden, für die Zuordnung im Monitor)
A19, A23, A24, A25, A26, A28 = "$0.0245", "$0.0265", "$0.0285", "$0.0305", "$0.0325", "$0.0365"  # A27 am 1.11.2026 gelöscht
A30, A36 = "$0.0225", "$0.0345"
ZONE = S("IANA time zone, e.g. Europe/Zurich, America/New_York, Asia/Tokyo")
routes = {
    "GET /v1/lei": route(
        A19, "Looks up a legal entity in the GLEIF LEI index by LEI, company name or ISIN: legal name, status, "
             "jurisdiction, legal and HQ address, LEI registration status and renewal date, direct and ultimate "
             "parent, number of subsidiaries and linked ISINs. For KYB, counterparty and compliance checks.",
        ["kyb", "compliance", "lei", "company-data", "finance"], {"name": "Nestle S.A."},
        {"lei": S("20-character LEI"), "name": S("Company name (full-text search)"), "isin": S("ISIN, e.g. US0378331005")},
        [], {"matches": 1, "entities": [{"lei": "HWUPKR0MPOU8FGXBT394", "legal_name": "Apple Inc.", "status": "ACTIVE",
             "jurisdiction": "US-CA", "lei_registration_status": "ISSUED", "isins_total": 120}]}),
    "GET /v1/timezone": route(
        A23, "Returns local time, UTC offset, abbreviation and DST status for an IANA time zone, the next daylight "
             "saving change, and optionally converts a time to another zone.",
        ["time", "timezone", "dst", "scheduling", "utility"], {"zone": "Europe/Zurich", "to": "America/New_York"},
        {"zone": ZONE, "time": S("ISO time, default now"), "to": S("Second zone to convert to")}, ["zone"],
        {"zone": "Europe/Zurich", "utc_offset": "+01:00", "dst_active": False,
         "next_transition": {"at_utc": "2027-03-28T01:00:00+00:00", "offset_after": "+02:00"}}),
    "GET /v1/meeting-window": route(
        A23, "Finds the common working-hours window (default 09-17 local) across 2-10 time zones on a date.",
        ["time", "timezone", "scheduling", "meetings"], {"zones": "Europe/Zurich,America/New_York"},
        {"zones": S("Comma-separated IANA zones"), "date": S("YYYY-MM-DD, default today"),
         "start_hour": S("Start of working day, default 9"), "end_hour": S("End of working day, default 17")},
        ["zones"], {"overlap": {"start_utc": "2026-11-02T14:00:00+00:00", "minutes": 120}}),
    "GET /v1/sun-moon": route(
        A24, "Computes sunrise, sunset, civil dawn and dusk, solar noon, day length, sun elevation, moon phase, "
             "illumination, moonrise and moonset for a location and date (polar day/night handled).",
        ["astronomy", "sun", "moon", "solar", "photography", "agriculture"], {"lat": "47.37", "lon": "8.54"},
        {"lat": S("Latitude"), "lon": S("Longitude"), "date": S("YYYY-MM-DD, default today"),
         "zone": S("IANA zone for the output times, default UTC")}, ["lat", "lon"],
        {"sun": {"sunrise": "2026-11-01T07:07:00+01:00", "sunset": "2026-11-01T17:05:00+01:00",
                 "day_length_hours": 9.97}, "moon": {"phase": "Waning Gibbous", "illumination_pct": 72.4}}),
    "GET /v1/treasury-rate": route(
        A25, "Returns the official quarterly US Treasury Reporting Rate of Exchange (foreign currency per USD) for "
             "a currency and date, as used for US federal accounting and tax reporting, with optional conversion.",
        ["fx", "accounting", "tax", "treasury", "finance"], {"currency": "EUR", "amount": "1000"},
        {"currency": S("ISO code (EUR, CHF, JPY...) or country name"), "date": S("YYYY-MM-DD, default today"),
         "amount": S("Amount in foreign currency to convert to USD")}, ["currency"],
        {"table_date": "2026-09-30", "rates": [{"country_currency": "Euro Zone-Euro", "foreign_per_usd": 0.861}]}),
    "GET /v1/vat": route(
        A26, "Returns EU VAT rates (standard, reduced, super-reduced, parking) for one or all 27 member states, "
             "recent rate changes, and calculates net, VAT and gross for an amount.",
        ["tax", "vat", "eu", "ecommerce", "invoicing"], {"country": "DE", "amount": "100"},
        {"country": S("EU country code (DE, FR, EL...) or name; empty = all"), "amount": S("Amount to calculate"),
         "rate": S("'standard' or a valid rate like 7"), "amount_includes_vat": S("true if amount is gross")},
        [], {"country_code": "DE", "standard": 19, "reduced": [7],
             "calculation": {"rate_pct": 19, "net": 100.0, "vat": 19.0, "gross": 119.0}}),
    "GET /v1/vin": route(
        A28, "Decodes a 17-character vehicle identification number (NHTSA vPIC): make, model, year, trim, body, "
             "engine, fuel, drive, plant, and validates the check digit.",
        ["automotive", "vin", "vehicles", "insurance", "reference"], {"vin": "1HGCM82633A004352"},
        {"vin": S("17-character VIN"), "model_year": S("Optional model year hint")}, ["vin"],
        {"decoded": {"make": "HONDA", "model": "Accord", "model_year": "2003", "trim": "EX-V6"},
         "check_digit_valid": True}),
    "GET /v1/iban": route(
        A30, "Validates an IBAN (ISO 13616: country format, length, check digits and, where defined, the national "
             "account check digit), formats it and splits it into bank code, branch code and account number, with "
             "SEPA membership and the bank name/BIC where a national bank directory exists. For payment, invoicing "
             "and onboarding agents. Does not prove that the account exists.",
        ["payments", "iban", "banking", "validation", "sepa", "finance"], {"iban": "DE89370400440532013000"},
        {"iban": S("IBAN, spaces allowed")}, ["iban"],
        {"valid": True, "formatted": "DE89 3704 0044 0532 0130 00", "country_code": "DE", "sepa": True,
         "bank_code": "37040044", "account_number": "0532013000",
         "bank": {"name": "Commerzbank", "bic": "COBADEFFXXX"}}),
    "GET /v1/bic": route(
        A30, "Validates a BIC/SWIFT code (8 or 11 characters): bank, country, location and branch code, test-BIC "
             "flag and known bank names.",
        ["payments", "bic", "swift", "banking", "validation"], {"bic": "UBSWCHZH80A"},
        {"bic": S("BIC/SWIFT code")}, ["bic"],
        {"valid": True, "bank_code": "UBSW", "country_code": "CH", "location_code": "ZH", "branch_code": "80A",
         "bank_names": ["UBS Switzerland AG - Zürich"]}),
    "GET /v1/country": route(
        A36, "ISO 3166 country lookup by alpha-2, alpha-3, numeric code or name (fuzzy): official name, codes, flag, "
             "official currencies (ISO 4217) and optionally all ISO 3166-2 subdivisions (states, cantons, regions).",
        ["reference", "iso", "country", "geography", "data-normalization"], {"code": "CH"},
        {"code": S("Alpha-2, alpha-3, numeric code or country name"),
         "subdivisions": S("true to list ISO 3166-2 subdivisions")}, ["code"],
        {"alpha_2": "CH", "alpha_3": "CHE", "numeric": "756", "name": "Switzerland",
         "official_name": "Swiss Confederation", "currencies": ["CHF"], "subdivisions_count": 26}),
    "GET /v1/currency": route(
        A36, "ISO 4217 currency lookup by code, numeric code or name: name, numeric code, minor units (decimal "
             "places for amounts) and the countries that use it officially.",
        ["reference", "iso", "currency", "fx", "payments", "data-normalization"], {"code": "CHF"},
        {"code": S("Alpha-3 code, numeric code or currency name")}, ["code"],
        {"code": "CHF", "numeric": "756", "name": "Swiss Franc", "minor_units": 2,
         "used_in": [{"alpha_2": "CH", "name": "Switzerland"}, {"alpha_2": "LI", "name": "Liechtenstein"}]}),
}

app.add_middleware(PaymentMiddlewareASGI, routes=routes, server=server)
app.title = f"Reference Data API ({MODE})"
