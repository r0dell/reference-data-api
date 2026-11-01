"""A30 IBAN/BIC-Prüfung und A36 ISO-Referenz (Währungen, Länder). Alles lokal, kein Netz.

Quellen: IBAN-Struktur nach ISO 13616 / SWIFT IBAN Registry und Bankverzeichnisse der Nationalbanken,
gebündelt im Paket schwifty (MIT). Länder/Währungen: ISO 3166 / ISO 4217 aus dem Debian-Paket iso-codes,
gebündelt in pycountry (LGPL). Nachkommastellen der Währungen: eigene Tabelle nach ISO 4217.
"""
from __future__ import annotations

import re

import pycountry
from schwifty import BIC, IBAN
from schwifty import exceptions as sx

SRC_IBAN = "ISO 13616 / SWIFT IBAN Registry structure and national bank directories (via schwifty)"
SRC_ISO = "ISO 3166-1/-2 and ISO 4217 (Debian iso-codes via pycountry)"

# ISO 4217: Währungen mit anderer Nachkommastellenzahl als 2
MINOR = {
    0: "BIF CLP DJF GNF ISK JPY KMF KRW PYG RWF UGX UYI VND VUV XAF XOF XPF".split(),
    3: "BHD IQD JOD KWD LYD OMR TND".split(),
    4: "CLF UYW".split(),
}
NO_MINOR = set("XAU XAG XPT XPD XDR XBA XBB XBC XBD XSU XUA XTS XXX".split())  # Metalle, Fonds, Testcodes


def _minor(code: str):
    if code in NO_MINOR:
        return None
    for n, codes in MINOR.items():
        if code in codes:
            return n
    return 2


def _iban_error(e: Exception) -> str:
    return {
        sx.InvalidChecksumDigits: "check digits wrong (typo or swapped digits)",
        sx.InvalidCountryCode: "unknown country code",
        sx.InvalidLength: "wrong length for this country",
        sx.InvalidStructure: "characters do not match the country format",
        sx.InvalidBBANChecksum: "national check digit of the account number is wrong",
    }.get(type(e), str(e))


def iban_check(iban: str) -> dict:
    raw = re.sub(r"[\s\-.]", "", iban or "").upper()
    if not raw:
        raise ValueError("Parameter 'iban' is required")
    if len(raw) > 34 or not raw.isalnum():
        raise ValueError("An IBAN has at most 34 letters and digits")
    out = {"input": iban, "iban": raw, "source": SRC_IBAN}
    try:
        i = IBAN(raw)
    except sx.SchwiftyException as e:
        out.update(valid=False, error=_iban_error(e))
        country = pycountry.countries.get(alpha_2=raw[:2])
        if country is not None:
            out["country"] = country.name
        return out
    bank = None
    try:
        b = i.bank
        if b:
            bank = {"name": b.get("name") if isinstance(b, dict) else getattr(b, "name", None),
                    "bic": str(i.bic) if i.bic else None}
    except Exception:
        bank = None
    country = pycountry.countries.get(alpha_2=i.country_code)
    out.update(
        valid=True,
        formatted=i.formatted,
        country_code=i.country_code,
        country=country.name if country else None,
        sepa=bool(i.in_sepa_zone),
        check_digits=i.checksum_digits,
        bank_code=i.bank_code or None,
        branch_code=i.branch_code or None,
        account_number=i.account_code or None,
        length=i.length,
        bank=bank,
        note="Valid format and check digits; this does not prove the account exists or who holds it.",
    )
    return out


def bic_check(bic: str) -> dict:
    raw = re.sub(r"\s", "", bic or "").upper()
    out = {"input": bic, "bic": raw, "source": SRC_IBAN}
    try:
        b = BIC(raw)
    except sx.SchwiftyException as e:
        out.update(valid=False, error=str(e))
        return out
    country = pycountry.countries.get(alpha_2=b.country_code)
    names = []
    try:
        names = list(b.bank_names or [])
    except Exception:
        pass
    out.update(valid=True, bank_code=b.bank_code, country_code=b.country_code,
               country=country.name if country else None, location_code=b.location_code,
               branch_code=b.branch_code or "XXX", is_test_bic=b.location_code[1:] == "0",
               bank_names=names[:5])
    return out


def _country(c) -> dict:
    subs = pycountry.subdivisions.get(country_code=c.alpha_2) or []
    curr = [x.alpha_3 for x in pycountry.currencies if x.alpha_3 in CURRENCY_OF.get(c.alpha_2, [])]
    return {"alpha_2": c.alpha_2, "alpha_3": c.alpha_3, "numeric": c.numeric, "name": c.name,
            "official_name": getattr(c, "official_name", None), "flag": getattr(c, "flag", None),
            "currencies": curr, "subdivisions_count": len(subs),
            "subdivision_types": sorted({s.type for s in subs})}


def country_info(code: str, subdivisions: bool = False) -> dict:
    q = (code or "").strip()
    if not q:
        raise ValueError("Parameter 'code' is required (alpha-2, alpha-3, numeric or name)")
    c = None
    if q.isdigit():
        c = pycountry.countries.get(numeric=q.zfill(3))
    elif len(q) == 2:
        c = pycountry.countries.get(alpha_2=q.upper())
    elif len(q) == 3:
        c = pycountry.countries.get(alpha_3=q.upper())
    if c is None:
        try:
            c = pycountry.countries.lookup(q)
        except LookupError:
            try:
                hits = pycountry.countries.search_fuzzy(q) if len(q) >= 4 else []
            except LookupError:
                hits = []
            if not hits:
                raise KeyError(f"No country found for '{q}'")
            c = hits[0]
    out = _country(c)
    if subdivisions:
        out["subdivisions"] = [{"code": s.code, "name": s.name, "type": s.type, "parent": s.parent_code}
                               for s in sorted(pycountry.subdivisions.get(country_code=c.alpha_2) or [],
                                               key=lambda s: s.code)]
    out["source"] = SRC_ISO
    return out


def currency_info(code: str) -> dict:
    q = (code or "").strip()
    if not q:
        raise ValueError("Parameter 'code' is required (alpha-3, numeric or name)")
    cur = None
    if q.isdigit():
        cur = pycountry.currencies.get(numeric=q.zfill(3))
    elif len(q) == 3:
        cur = pycountry.currencies.get(alpha_3=q.upper())
    if cur is None:
        try:
            cur = pycountry.currencies.lookup(q)
        except LookupError:
            hit = [x for x in pycountry.currencies if q.lower() in x.name.lower()]
            if not hit:
                raise KeyError(f"No ISO 4217 currency found for '{q}'")
            cur = hit[0]
    users = sorted(cc for cc, lst in CURRENCY_OF.items() if cur.alpha_3 in lst)
    return {"code": cur.alpha_3, "numeric": cur.numeric, "name": cur.name, "minor_units": _minor(cur.alpha_3),
            "used_in": [{"alpha_2": cc, "name": pycountry.countries.get(alpha_2=cc).name}
                        for cc in users if pycountry.countries.get(alpha_2=cc)],
            "source": SRC_ISO}


# Amtliche Landeswährung(en) je Land (ISO 4217, Stand 2026; Bulgarien seit 1.1.2026 EUR)
_EUR = "AD AT BE BG CY DE EE ES FI FR GR HR IE IT LT LU LV MC ME MT NL PT SI SK SM VA XK GF GP MQ YT RE BL MF PM AX TF".split()
_USD = "US EC SV PA TL FM MH PW AS GU MP PR VI VG TC UM IO BQ ZW".split()
CURRENCY_OF: dict[str, list[str]] = {cc: ["EUR"] for cc in _EUR}
CURRENCY_OF.update({cc: ["USD"] for cc in _USD})
CURRENCY_OF["PA"] = ["PAB", "USD"]
CURRENCY_OF["SV"] = ["USD"]
CURRENCY_OF["ZW"] = ["ZWG", "USD"]
_SINGLE = {
    "AE": "AED", "AF": "AFN", "AL": "ALL", "AM": "AMD", "AO": "AOA", "AR": "ARS", "AU": "AUD", "AW": "AWG",
    "AZ": "AZN", "BA": "BAM", "BB": "BBD", "BD": "BDT", "BH": "BHD", "BI": "BIF", "BM": "BMD", "BN": "BND",
    "BO": "BOB", "BR": "BRL", "BS": "BSD", "BT": "BTN", "BW": "BWP", "BY": "BYN", "BZ": "BZD", "CA": "CAD",
    "CD": "CDF", "CH": "CHF", "LI": "CHF", "CL": "CLP", "CN": "CNY", "CO": "COP", "CR": "CRC", "CU": "CUP",
    "CV": "CVE", "CZ": "CZK", "DJ": "DJF", "DK": "DKK", "FO": "DKK", "GL": "DKK", "DO": "DOP", "DZ": "DZD",
    "EG": "EGP", "ER": "ERN", "ET": "ETB", "FJ": "FJD", "FK": "FKP", "GB": "GBP", "IM": "GBP", "JE": "GBP",
    "GG": "GBP", "GE": "GEL", "GH": "GHS", "GI": "GIP", "GM": "GMD", "GN": "GNF", "GT": "GTQ", "GY": "GYD",
    "HK": "HKD", "HN": "HNL", "HT": "HTG", "HU": "HUF", "ID": "IDR", "IL": "ILS", "IN": "INR", "IQ": "IQD",
    "IR": "IRR", "IS": "ISK", "JM": "JMD", "JO": "JOD", "JP": "JPY", "KE": "KES", "KG": "KGS", "KH": "KHR",
    "KM": "KMF", "KP": "KPW", "KR": "KRW", "KW": "KWD", "KY": "KYD", "KZ": "KZT", "LA": "LAK", "LB": "LBP",
    "LK": "LKR", "LR": "LRD", "LS": "LSL", "LY": "LYD", "MA": "MAD", "EH": "MAD", "MD": "MDL", "MG": "MGA",
    "MK": "MKD", "MM": "MMK", "MN": "MNT", "MO": "MOP", "MR": "MRU", "MU": "MUR", "MV": "MVR", "MW": "MWK",
    "MX": "MXN", "MY": "MYR", "MZ": "MZN", "NA": "NAD", "NG": "NGN", "NI": "NIO", "NO": "NOK", "SJ": "NOK",
    "BV": "NOK", "NP": "NPR", "NZ": "NZD", "CK": "NZD", "NU": "NZD", "PN": "NZD", "TK": "NZD", "OM": "OMR",
    "PE": "PEN", "PG": "PGK", "PH": "PHP", "PK": "PKR", "PL": "PLN", "PY": "PYG", "QA": "QAR", "RO": "RON",
    "RS": "RSD", "RU": "RUB", "RW": "RWF", "SA": "SAR", "SB": "SBD", "SC": "SCR", "SD": "SDG", "SE": "SEK",
    "SG": "SGD", "SH": "SHP", "SL": "SLE", "SO": "SOS", "SR": "SRD", "SS": "SSP", "ST": "STN", "SY": "SYP",
    "SZ": "SZL", "TH": "THB", "TJ": "TJS", "TM": "TMT", "TN": "TND", "TO": "TOP", "TR": "TRY", "TT": "TTD",
    "TW": "TWD", "TZ": "TZS", "UA": "UAH", "UG": "UGX", "UY": "UYU", "UZ": "UZS", "VE": "VES", "VN": "VND",
    "VU": "VUV", "WS": "WST", "YE": "YER", "ZA": "ZAR", "ZM": "ZMW", "KI": "AUD", "NR": "AUD", "TV": "AUD",
    "CX": "AUD", "CC": "AUD", "NF": "AUD", "HM": "AUD", "CW": "XCG", "SX": "XCG",
    "AG": "XCD", "DM": "XCD", "GD": "XCD", "KN": "XCD", "LC": "XCD", "VC": "XCD", "AI": "XCD", "MS": "XCD",
    "BJ": "XOF", "BF": "XOF", "CI": "XOF", "GW": "XOF", "ML": "XOF", "NE": "XOF", "SN": "XOF", "TG": "XOF",
    "CM": "XAF", "CF": "XAF", "TD": "XAF", "CG": "XAF", "GQ": "XAF", "GA": "XAF",
    "PF": "XPF", "NC": "XPF", "WF": "XPF",
}
CURRENCY_OF.update({k: [v] for k, v in _SINGLE.items()})
CURRENCY_OF["LS"] = ["LSL", "ZAR"]
CURRENCY_OF["NA"] = ["NAD", "ZAR"]
CURRENCY_OF["BT"] = ["BTN", "INR"]
CURRENCY_OF["CU"] = ["CUP"]
