"""Intégration CardDAV Birthdays pour Home Assistant."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import BirthdayCoordinator, CardDavBirthdaysConfigEntry

PLATFORMS: list[Platform] = [Platform.CALENDAR]


async def async_setup_entry(
    hass: HomeAssistant, entry: CardDavBirthdaysConfigEntry
) -> bool:
    """Configurer une entrée de configuration."""
    coordinator = BirthdayCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: CardDavBirthdaysConfigEntry
) -> bool:
    """Décharger une entrée de configuration."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(
    hass: HomeAssistant, entry: CardDavBirthdaysConfigEntry
) -> None:
    """Recharger l'intégration quand les options changent."""
    await hass.config_entries.async_reload(entry.entry_id)
