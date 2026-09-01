"""Entité calendrier exposant les anniversaires des contacts CardDAV."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.translation import async_get_translations
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .carddav import Birthday
from .const import (
    CONF_SHOW_AGE,
    DEFAULT_SHOW_AGE,
    DOMAIN,
    LOOKAHEAD_DAYS,
    TRANSLATION_CATEGORY,
)
from .coordinator import BirthdayCoordinator, CardDavBirthdaysConfigEntry

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EventStrings:
    """Libellés des événements, traduits dans la langue de Home Assistant.

    Les valeurs par défaut (anglais neutre) servent de repli si les traductions
    ne sont pas chargées ; elles sont surchargées par la section "event" de
    translations/<lang>.json.
    """

    with_age: str = "{name} ({age})"
    with_age_one: str = "{name} ({age})"
    description: str = "Birthday"
    description_with_date: str = "Birthday — born on {date}"
    date_format: str = "%Y-%m-%d"

    @classmethod
    async def async_load(cls, hass: HomeAssistant) -> EventStrings:
        """Charger les libellés depuis les fichiers de traduction."""
        defaults = cls()
        try:
            translations = await async_get_translations(
                hass, hass.config.language, TRANSLATION_CATEGORY, {DOMAIN}
            )
        except Exception:  # noqa: BLE001 - repli silencieux sur l'anglais
            _LOGGER.debug("Traductions indisponibles, libellés par défaut", exc_info=True)
            return defaults

        prefix = f"component.{DOMAIN}.{TRANSLATION_CATEGORY}."
        values = {
            field: translations.get(f"{prefix}{field}", getattr(defaults, field))
            for field in (
                "with_age",
                "with_age_one",
                "description",
                "description_with_date",
                "date_format",
            )
        }
        return cls(**values)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CardDavBirthdaysConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Ajouter l'entité calendrier."""
    strings = await EventStrings.async_load(hass)
    async_add_entities([BirthdayCalendarEntity(entry.runtime_data, strings)])


class BirthdayCalendarEntity(CoordinatorEntity[BirthdayCoordinator], CalendarEntity):
    """Calendrier en lecture seule des anniversaires."""

    _attr_has_entity_name = True
    _attr_translation_key = "birthdays"

    def __init__(
        self, coordinator: BirthdayCoordinator, strings: EventStrings | None = None
    ) -> None:
        """Initialiser l'entité."""
        super().__init__(coordinator)
        self._strings = strings or EventStrings()
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_birthdays"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="CardDAV",
            model="Anniversaires des contacts",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def _show_age(self) -> bool:
        """Afficher l'âge dans le titre de l'événement."""
        return self.coordinator.config_entry.options.get(CONF_SHOW_AGE, DEFAULT_SHOW_AGE)

    def _summary(self, birthday: Birthday, age: int | None) -> str:
        """Composer le titre de l'événement."""
        if not self._show_age or age is None or not 0 <= age <= 130:
            return birthday.name
        template = self._strings.with_age_one if age == 1 else self._strings.with_age
        try:
            return template.format(name=birthday.name, age=age)
        except (KeyError, IndexError):
            return f"{birthday.name} ({age})"

    def _description(self, birthday: Birthday) -> str:
        """Composer la description de l'événement."""
        if birthday.year is None:
            return self._strings.description
        born = date(birthday.year, birthday.month, birthday.day)
        try:
            formatted = born.strftime(self._strings.date_format)
            return self._strings.description_with_date.format(date=formatted)
        except (KeyError, IndexError, ValueError):
            return self._strings.description

    def _build_event(self, birthday: Birthday, year: int) -> CalendarEvent:
        """Construire l'événement journée entière d'une occurrence."""
        start = birthday.occurrence(year)
        return CalendarEvent(
            summary=self._summary(birthday, birthday.age_at(year)),
            description=self._description(birthday),
            start=start,
            end=start + timedelta(days=1),
            uid=f"{birthday.uid}-{year}",
        )

    def _events_between(self, start: date, end: date) -> list[CalendarEvent]:
        """Développer les anniversaires sur une plage de dates."""
        events: list[CalendarEvent] = []
        for birthday in self.coordinator.data or []:
            for year in range(start.year, end.year + 1):
                occurrence = birthday.occurrence(year)
                if start <= occurrence < end:
                    events.append(self._build_event(birthday, year))
        events.sort(key=lambda event: (event.start, event.summary))
        return events

    @property
    def event(self) -> CalendarEvent | None:
        """Prochain anniversaire (ou celui du jour)."""
        today = dt_util.now().date()
        events = self._events_between(today, today + timedelta(days=LOOKAHEAD_DAYS))
        return events[0] if events else None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Renvoyer les anniversaires compris dans la plage demandée."""
        return self._events_between(
            dt_util.as_local(start_date).date(), dt_util.as_local(end_date).date()
        )
