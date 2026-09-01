"""Constantes de l'intégration CardDAV Birthdays."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "carddav_birthdays"

CONF_ADDRESSBOOKS: Final = "addressbooks"
CONF_SHOW_AGE: Final = "show_age"
CONF_UPDATE_INTERVAL: Final = "update_interval_hours"

DEFAULT_URL: Final = "https://sync.infomaniak.com/"
DEFAULT_UPDATE_INTERVAL: Final = 24
DEFAULT_SHOW_AGE: Final = True

# Fenêtre maximale explorée pour trouver le prochain anniversaire.
LOOKAHEAD_DAYS: Final = 400

# Catégorie de traduction personnalisée (clés "event" de translations/<lang>.json).
TRANSLATION_CATEGORY: Final = "event"
