"""Flux de configuration de l'intégration CardDAV Birthdays."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .carddav import AddressBook, CardDavAuthError, CardDavClient, CardDavError
from .const import (
    CONF_ADDRESSBOOKS,
    CONF_SHOW_AGE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_SHOW_AGE,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_URL,
    DOMAIN,
)
from .coordinator import CardDavBirthdaysConfigEntry

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL, default=DEFAULT_URL): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)
STEP_REAUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        )
    }
)


class CardDavBirthdaysConfigFlow(ConfigFlow, domain=DOMAIN):
    """Gérer la configuration initiale."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialiser le flux."""
        self._data: dict[str, Any] = {}
        self._addressbooks: list[AddressBook] = []

    async def _async_discover(
        self, url: str, username: str, password: str
    ) -> list[AddressBook]:
        """Tester les identifiants et lister les carnets d'adresses."""
        client = CardDavClient(
            async_get_clientsession(self.hass), url, username, password
        )
        return await client.async_discover_addressbooks()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Demander l'URL et les identifiants."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                self._addressbooks = await self._async_discover(
                    user_input[CONF_URL],
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                )
            except CardDavAuthError:
                errors["base"] = "invalid_auth"
            except CardDavError as err:
                _LOGGER.debug("Connexion CardDAV impossible : %s", err)
                errors["base"] = "cannot_connect"
            else:
                unique_id = (
                    f"{user_input[CONF_URL]}::{user_input[CONF_USERNAME]}".lower()
                )
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                self._data = dict(user_input)
                return await self.async_step_addressbooks()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_addressbooks(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choisir les carnets d'adresses à surveiller."""
        if user_input is not None:
            return self.async_create_entry(
                title=f"Anniversaires ({self._data[CONF_USERNAME]})",
                data={**self._data, CONF_ADDRESSBOOKS: user_input[CONF_ADDRESSBOOKS]},
                options={
                    CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                    CONF_SHOW_AGE: DEFAULT_SHOW_AGE,
                },
            )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_ADDRESSBOOKS,
                    default=[book.url for book in self._addressbooks],
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value=book.url, label=book.name)
                            for book in self._addressbooks
                        ],
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                )
            }
        )
        return self.async_show_form(step_id="addressbooks", data_schema=schema)

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Démarrer une ré-authentification."""
        self._data = dict(entry_data)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Demander un nouveau mot de passe."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await self._async_discover(
                    self._data[CONF_URL],
                    self._data[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                )
            except CardDavAuthError:
                errors["base"] = "invalid_auth"
            except CardDavError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_SCHEMA,
            errors=errors,
            description_placeholders={"username": self._data.get(CONF_USERNAME, "")},
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: CardDavBirthdaysConfigEntry,
    ) -> OptionsFlow:
        """Renvoyer le flux d'options."""
        return CardDavBirthdaysOptionsFlow()


class CardDavBirthdaysOptionsFlow(OptionsFlow):
    """Gérer les options (fréquence, affichage de l'âge)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Afficher et enregistrer les options."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_UPDATE_INTERVAL: int(user_input[CONF_UPDATE_INTERVAL]),
                    CONF_SHOW_AGE: user_input[CONF_SHOW_AGE],
                }
            )

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_UPDATE_INTERVAL,
                    default=options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=1, max=336, step=1, mode=NumberSelectorMode.BOX
                    )
                ),
                vol.Required(
                    CONF_SHOW_AGE,
                    default=options.get(CONF_SHOW_AGE, DEFAULT_SHOW_AGE),
                ): BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
