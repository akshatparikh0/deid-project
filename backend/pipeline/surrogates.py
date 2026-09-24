"""
Deterministic fake-value generation for 'pseudo' mode: the same (category,
value) pair always produces the same surrogate, so a person or MRN that
recurs across a document — or across documents processed with the same
process, since the mapping is derived rather than random — reads
consistently in the de-identified output, per Safe Harbor's pseudonymization
guidance. No third-party faker dependency: a small deterministic PRNG seeded
from the value's hash drives lookups into short built-in name/place lists.
"""
import hashlib
import re

_FIRST_NAMES = [
    "Karen", "Marcus", "Anita", "Owen", "Priya", "Daniel", "Rosa", "Trevor",
    "Ingrid", "Samuel", "Naomi", "Felix", "Yusuf", "Clara", "Dmitri", "Leah",
]
_LAST_NAMES = [
    "Whitfield", "Ellery", "Ruiz", "Fitzhugh", "Nandakumar", "Okafor",
    "Bergstrom", "Halvorsen", "Castellano", "Vance", "Bramwell", "Osei",
]
_STREETS = ["Aldergrove Way", "Kestrel Lane", "Birchwood Ave", "Fenwick Road", "Marston Court"]
_CITIES = ["Fairmont", "Meridian Falls", "Cedar Hollow", "Northbridge", "Ashford"]


def _seeded_int(key, modulus):
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % modulus


def make_surrogate(category, value):
    key = f"{category}:{value.lower()}"

    if category in ("name", "patient_name", "physician_name"):
        first = _FIRST_NAMES[_seeded_int(key + "f", len(_FIRST_NAMES))]
        last = _LAST_NAMES[_seeded_int(key + "l", len(_LAST_NAMES))]
        suffix_match = re.search(r",?\s*(MD|RN|DO|NP|PA|MSW)\b", value)
        return f"{first} {last}" + (f", {suffix_match.group(1)}" if suffix_match else "")

    if category == "facility":
        return f"{_CITIES[_seeded_int(key + 'c', len(_CITIES))]} Medical Center"

    if category == "date":
        m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", value)
        if m:
            month, day, year = int(m.group(1)), int(m.group(2)), m.group(3)
            month = ((month - 1 + _seeded_int(key + "m", 6) + 1) % 12) + 1
            day = ((day - 1 + _seeded_int(key + "d", 10) + 1) % 28) + 1
            return f"{month:02d}/{day:02d}/{year}"
        return value

    if category == "geo":
        num = 100 + _seeded_int(key + "n", 899)
        street = _STREETS[_seeded_int(key + "s", len(_STREETS))]
        city = _CITIES[_seeded_int(key + "c", len(_CITIES))]
        return f"{num} {street}, {city}"

    if category in ("phone", "fax"):
        exch = 200 + _seeded_int(key + "e", 799)
        line = _seeded_int(key + "n2", 9999)
        return f"(360) {exch:03d}-{line:04d}"

    if category == "email":
        first = _FIRST_NAMES[_seeded_int(key + "f", len(_FIRST_NAMES))].lower()
        return f"{first[0]}.{_LAST_NAMES[_seeded_int(key + 'l', len(_LAST_NAMES))].lower()}@example-mail.com"

    if category == "ssn":
        return f"{100 + _seeded_int(key + 'a', 899)}-{10 + _seeded_int(key + 'b', 89)}-{1000 + _seeded_int(key + 'c', 8999)}"

    if category == "ip":
        return f"10.{_seeded_int(key + 'a', 255)}.{_seeded_int(key + 'b', 255)}.{_seeded_int(key + 'c', 255)}"

    # Fallback for the remaining identifier-style categories (mrn, plan,
    # account, license, vehicle, device, url, biometric, photo, other):
    # preserve length/shape but swap alphanumerics for a shuffled surrogate.
    out = []
    for ch in value:
        if ch.isdigit():
            out.append(str(_seeded_int(key + ch + str(len(out)), 10)))
        elif ch.isalpha():
            base = ord("A") if ch.isupper() else ord("a")
            out.append(chr(base + _seeded_int(key + ch + str(len(out)), 26)))
        else:
            out.append(ch)
    return "".join(out)
