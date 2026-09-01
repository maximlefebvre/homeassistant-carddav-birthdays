"""Test de l'entité calendrier avec des stubs Home Assistant."""

import asyncio
import importlib
import json
import sys
import types
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

INT_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "carddav_birthdays"


def _module(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


class _Subscriptable:
    def __class_getitem__(cls, item):
        return cls


class CalendarEntity(_Subscriptable):
    pass


@dataclass
class CalendarEvent:
    summary: str
    start: object
    end: object
    description: str | None = None
    uid: str | None = None


class CoordinatorEntity(_Subscriptable):
    def __init__(self, coordinator):
        self.coordinator = coordinator


class DataUpdateCoordinator(_Subscriptable):
    def __init__(self, *args, **kwargs):
        pass


NOW = datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)

# --- stubs Home Assistant -------------------------------------------------- #
_module("homeassistant")
_module("homeassistant.components")
_module("homeassistant.helpers")
_module("homeassistant.util")
_module("homeassistant.components.calendar", CalendarEntity=CalendarEntity, CalendarEvent=CalendarEvent)
_module("homeassistant.core", HomeAssistant=object, callback=lambda func: func)
_module("homeassistant.config_entries", ConfigEntry=_Subscriptable)
_module("homeassistant.const", CONF_PASSWORD="password", CONF_URL="url", CONF_USERNAME="username",
        Platform=types.SimpleNamespace(CALENDAR="calendar"))
_module("homeassistant.exceptions", ConfigEntryAuthFailed=type("ConfigEntryAuthFailed", (Exception,), {}))
_module("homeassistant.helpers.aiohttp_client", async_get_clientsession=lambda hass: None)
_module("homeassistant.helpers.device_registry",
        DeviceInfo=dict, DeviceEntryType=types.SimpleNamespace(SERVICE="service"))
_module("homeassistant.helpers.entity_platform", AddEntitiesCallback=object)
_module("homeassistant.helpers.update_coordinator",
        CoordinatorEntity=CoordinatorEntity, DataUpdateCoordinator=DataUpdateCoordinator,
        UpdateFailed=type("UpdateFailed", (Exception,), {}))
_module("homeassistant.util.dt", now=lambda: NOW, as_local=lambda value: value)


async def _fake_get_translations(hass, language, category, integrations):
    """Charger la vraie section 'event' de translations/<lang>.json."""
    path = INT_DIR / "translations" / f"{language}.json"
    if not path.exists():
        path = INT_DIR / "translations" / "en.json"
    data = json.loads(path.read_text())
    domain = next(iter(integrations))
    return {
        f"component.{domain}.{category}.{key}": value
        for key, value in data.get(category, {}).items()
    }


_module("homeassistant.helpers.translation", async_get_translations=_fake_get_translations)

_pkg = types.ModuleType("cdb")
_pkg.__path__ = [str(INT_DIR)]
sys.modules["cdb"] = _pkg

carddav = importlib.import_module("cdb.carddav")
calendar_module = importlib.import_module("cdb.calendar")
Birthday = carddav.Birthday


class FakeEntry:
    entry_id = "abc123"
    title = "Anniversaires (AB12345)"
    options: dict = {}


class FakeCoordinator:
    def __init__(self, data, options=None):
        self.data = data
        self.config_entry = FakeEntry()
        self.config_entry.options = options or {}


BIRTHDAYS = [
    Birthday("1", "Renaud Lefebvre", 4, 12, 1987),
    Birthday("2", "Zoé Martin", 2, 29, 2000),
    Birthday("3", "Client Pro", 11, 3, None),
]


class FakeHass:
    def __init__(self, language):
        self.config = types.SimpleNamespace(language=language)


def _strings(language):
    return asyncio.run(calendar_module.EventStrings.async_load(FakeHass(language)))


def _entity(options=None, language=None, birthdays=None):
    strings = _strings(language) if language else None
    coordinator = FakeCoordinator(BIRTHDAYS if birthdays is None else birthdays, options)
    return calendar_module.BirthdayCalendarEntity(coordinator, strings)


def test_year_expansion():
    entity = _entity()
    events = entity._events_between(date(2026, 1, 1), date(2027, 1, 1))
    assert [(event.start, event.summary) for event in events] == [
        (date(2026, 2, 28), "Zoé Martin (26)"),   # 2026 non bissextile
        (date(2026, 4, 12), "Renaud Lefebvre (39)"),
        (date(2026, 11, 3), "Client Pro"),            # pas d'année de naissance
    ], events
    assert events[0].end == date(2026, 3, 1)
    assert events[1].uid == "1-2026"
    assert events[1].description == "Birthday — born on 1987-04-12"
    assert events[2].description == "Birthday"

    leap = entity._events_between(date(2028, 1, 1), date(2029, 1, 1))
    assert leap[0].start == date(2028, 2, 29), leap[0]


def test_multi_year_range():
    entity = _entity()
    events = entity._events_between(date(2026, 12, 1), date(2027, 5, 1))
    assert [event.start for event in events] == [date(2027, 2, 28), date(2027, 4, 12)]


def test_bounds():
    entity = _entity()
    assert len(entity._events_between(date(2026, 4, 12), date(2026, 4, 13))) == 1
    assert entity._events_between(date(2026, 4, 13), date(2026, 4, 14)) == []


def test_show_age_option():
    entity = _entity({"show_age": False}, language="fr")
    events = entity._events_between(date(2026, 4, 1), date(2026, 5, 1))
    assert events[0].summary == "Renaud Lefebvre"


def test_next_event():
    entity = _entity()
    assert entity.event.start == date(2026, 4, 12)
    assert calendar_module.BirthdayCalendarEntity(FakeCoordinator([])).event is None


def test_async_get_events():
    entity = _entity()
    events = asyncio.run(
        entity.async_get_events(
            None,
            datetime(2026, 11, 1, tzinfo=timezone.utc),
            datetime(2026, 12, 1, tzinfo=timezone.utc),
        )
    )
    assert [event.summary for event in events] == ["Client Pro"]


def test_localised_strings():
    """Les libellés suivent la langue de Home Assistant."""
    fr = _entity(language="fr")
    events = fr._events_between(date(2026, 4, 1), date(2026, 5, 1))
    assert events[0].summary == "Renaud Lefebvre (39 ans)"
    assert events[0].description == "Anniversaire — né(e) le 12/04/1987"

    en = _entity(language="en")
    events = en._events_between(date(2026, 4, 1), date(2026, 5, 1))
    assert events[0].summary == "Renaud Lefebvre (39)"
    assert events[0].description == "Birthday — born on 1987-04-12"

    # langue non traduite -> repli sur l'anglais
    de = _entity(language="de")
    assert de._events_between(date(2026, 4, 1), date(2026, 5, 1))[0].summary == (
        "Renaud Lefebvre (39)"
    )

    # singulier français
    bebe = [Birthday("9", "Bébé", 4, 12, 2025)]
    entity = _entity(language="fr", birthdays=bebe)
    assert entity._events_between(date(2026, 4, 1), date(2026, 5, 1))[0].summary == (
        "Bébé (1 an)"
    )
    entity = _entity(language="en", birthdays=bebe)
    assert entity._events_between(date(2026, 4, 1), date(2026, 5, 1))[0].summary == (
        "Bébé (1)"
    )


if __name__ == "__main__":
    test_year_expansion()
    test_localised_strings()
    test_multi_year_range()
    test_bounds()
    test_show_age_option()
    test_next_event()
    test_async_get_events()
    print("entité calendrier : OK")
