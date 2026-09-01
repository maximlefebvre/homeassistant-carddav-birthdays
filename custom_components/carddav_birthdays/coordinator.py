"""Coordinateur de rafraîchissement des anniversaires CardDAV."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .carddav import Birthday, CardDavAuthError, CardDavClient, CardDavError
from .const import (
    CONF_ADDRESSBOOKS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

class BirthdayCoordinator(DataUpdateCoordinator[list[Birthday]]):
    """Interroge le serveur CardDAV une fois par jour (ou par semaine)."""

    config_entry: CardDavBirthdaysConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: CardDavBirthdaysConfigEntry
    ) -> None:
        """Initialiser le coordinateur."""
        hours = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(hours=hours),
        )
        self.client = CardDavClient(
            async_get_clientsession(hass),
            entry.data[CONF_URL],
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD],
        )
        self.addressbooks: list[str] = list(entry.data[CONF_ADDRESSBOOKS])

    async def _async_update_data(self) -> list[Birthday]:
        """Récupérer les anniversaires depuis le serveur."""
        try:
            birthdays = await self.client.async_fetch_birthdays(self.addressbooks)
        except CardDavAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except CardDavError as err:
            raise UpdateFailed(str(err)) from err
        _LOGGER.debug("%s anniversaires récupérés", len(birthdays))
        return birthdays


CardDavBirthdaysConfigEntry = ConfigEntry[BirthdayCoordinator]
