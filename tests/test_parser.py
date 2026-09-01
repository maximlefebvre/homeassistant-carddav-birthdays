"""Tests du parseur vCard (sans Home Assistant)."""

import importlib.util
import sys
from datetime import date
from pathlib import Path

_MODULE = Path(__file__).resolve().parents[1] / "custom_components" / "carddav_birthdays" / "carddav.py"
_spec = importlib.util.spec_from_file_location("cdb_carddav", _MODULE)
carddav = importlib.util.module_from_spec(_spec)
sys.modules["cdb_carddav"] = carddav
_spec.loader.exec_module(carddav)

Birthday = carddav.Birthday
parse_vcard = carddav.parse_vcard
split_vcards = carddav.split_vcards

CARDS = """BEGIN:VCARD
VERSION:3.0
UID:1
FN:Renaud Lefebvre
N:Lefebvre;Renaud;;;
BDAY:1987-04-12
END:VCARD
BEGIN:VCARD
VERSION:4.0
UID:2
FN:Zoé Martin
BDAY:--0229
END:VCARD
BEGIN:VCARD
VERSION:3.0
UID:3
N:Durand;Jean-Pierre;;;
BDAY;VALUE=DATE:19601231
END:VCARD
BEGIN:VCARD
VERSION:3.0
UID:4
FN:Sans anniversaire
END:VCARD
BEGIN:VCARD
VERSION:2.1
UID:5
FN;CHARSET=UTF-8;ENCODING=QUOTED-PRINTABLE:Ana=C3=AFs Fran=C3=A7ois
BDAY:1992-07-05
END:VCARD
BEGIN:VCARD
VERSION:3.0
UID:6
FN:Apple Contact
BDAY;X-APPLE-OMIT-YEAR=1604:1604-11-03
END:VCARD
BEGIN:VCARD
VERSION:3.0
UID:7
FN:Ligne
  repliee
BDAY:1975-01-09
END:VCARD
BEGIN:VCARD
VERSION:3.0
UID:8
FN:Date invalide
BDAY:circa 1800
END:VCARD
"""


def test_split():
    cards = split_vcards(CARDS)
    assert len(cards) == 8, len(cards)


def test_parse():
    parsed = {}
    for card in split_vcards(CARDS):
        birthday = parse_vcard(card)
        if birthday:
            parsed[birthday.uid] = birthday

    assert set(parsed) == {"1", "2", "3", "5", "6", "7"}, sorted(parsed)

    assert parsed["1"] == Birthday("1", "Renaud Lefebvre", 4, 12, 1987)
    assert parsed["2"] == Birthday("2", "Zoé Martin", 2, 29, None)
    # FN absent -> reconstruit depuis N (prénom + nom)
    assert parsed["3"] == Birthday("3", "Jean-Pierre Durand", 12, 31, 1960)
    assert parsed["5"].name == "Anaïs François"
    assert parsed["6"].year is None and (parsed["6"].month, parsed["6"].day) == (11, 3)
    assert parsed["7"].name == "Ligne repliee"


def test_occurrences():
    zoe = Birthday("2", "Zoé", 2, 29, 2000)
    assert zoe.occurrence(2028) == date(2028, 2, 29)
    assert zoe.occurrence(2027) == date(2027, 2, 28)  # année non bissextile
    assert zoe.age_at(2028) == 28

    renaud = Birthday("1", "Renaud", 4, 12, 1987)
    assert renaud.occurrence(2026) == date(2026, 4, 12)
    assert renaud.age_at(2026) == 39
    assert Birthday("x", "X", 4, 12, None).age_at(2026) is None


if __name__ == "__main__":
    test_split()
    test_parse()
    test_occurrences()
    print("parseur : OK")
