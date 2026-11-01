"""Mehrwertsteuersätze der 27 EU-Staaten (A26).

Gepflegte Tabelle, Stand VERIFIED. Bei jeder Satzänderung hier nachführen und VERIFIED setzen.
Geprüft gegen: Steuerverwaltungen (vero.fi, emta.ee), Gesetz LT XV-287, Übersichten asd-int.com (06/2026),
eurocompta.eu (09/2026). Produktgenaue Zuordnung: EU-Kommission, Datenbank «Taxes in Europe» (TEDB).

standard: Normalsatz; reduced: ermässigte Sätze; super_reduced: < 5 %; parking: Zwischensatz.
"""
VERIFIED = "2026-11-01"

RATES = {
    "AT": ("Austria", 20, [10, 13], None, None, "EUR"),
    "BE": ("Belgium", 21, [6, 12], None, 12, "EUR"),
    "BG": ("Bulgaria", 20, [9], None, None, "EUR"),
    "HR": ("Croatia", 25, [5, 13], None, None, "EUR"),
    "CY": ("Cyprus", 19, [5, 9], None, None, "EUR"),
    "CZ": ("Czechia", 21, [12], None, None, "CZK"),
    "DK": ("Denmark", 25, [], None, None, "DKK"),
    "EE": ("Estonia", 24, [9, 13], None, None, "EUR"),
    "FI": ("Finland", 25.5, [10, 13.5], None, None, "EUR"),
    "FR": ("France", 20, [5.5, 10], 2.1, None, "EUR"),
    "DE": ("Germany", 19, [7], None, None, "EUR"),
    "EL": ("Greece", 24, [6, 13], None, None, "EUR"),
    "HU": ("Hungary", 27, [5, 18], None, None, "HUF"),
    "IE": ("Ireland", 23, [9, 13.5], 4.8, 13.5, "EUR"),
    "IT": ("Italy", 22, [5, 10], 4, None, "EUR"),
    "LV": ("Latvia", 21, [5, 12], None, None, "EUR"),
    "LT": ("Lithuania", 21, [5, 12], None, None, "EUR"),
    "LU": ("Luxembourg", 17, [8], 3, 14, "EUR"),
    "MT": ("Malta", 18, [5, 7], None, None, "EUR"),
    "NL": ("Netherlands", 21, [9], None, None, "EUR"),
    "PL": ("Poland", 23, [5, 8], None, None, "PLN"),
    "PT": ("Portugal", 23, [6, 13], None, None, "EUR"),
    "RO": ("Romania", 21, [11], None, None, "RON"),
    "SK": ("Slovakia", 23, [5, 19], None, None, "EUR"),
    "SI": ("Slovenia", 22, [5, 9.5], None, None, "EUR"),
    "ES": ("Spain", 21, [10], 4, None, "EUR"),
    "SE": ("Sweden", 25, [6, 12], None, None, "SEK"),
}

# Satzänderungen seit 2025 (für Agenten, die alte Rechnungen prüfen)
CHANGES = [
    {"country": "SK", "date": "2025-01-01", "change": "standard 20 -> 23; new reduced 19; 10 -> 5"},
    {"country": "EE", "date": "2025-01-01", "change": "accommodation 9 -> 13; press 5 -> 9"},
    {"country": "EE", "date": "2025-07-01", "change": "standard 22 -> 24"},
    {"country": "RO", "date": "2025-08-01", "change": "standard 19 -> 21; reduced 5 and 9 -> 11"},
    {"country": "FI", "date": "2026-01-01", "change": "reduced 14 -> 13.5 (food, restaurants, books, medicines, "
                                                     "transport, accommodation); 10 kept for newspapers"},
    {"country": "LT", "date": "2026-01-01", "change": "9 abolished; accommodation, passenger transport, culture "
                                                     "-> 12; books -> 5; heating and hot water -> 21"},
]

ALIASES = {"GR": "EL", "GREECE": "EL", "UK": None, "GB": None}
