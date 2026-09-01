"""Constantes de l'intégration CardDAV Birthdays."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "carddav_birthdays"

CONF_ADDRESSBOOKS: Final = "addressbooks"
CONF_SHOW_AGE: Final = "show_age"
CONF_NAME_FORMAT: Final = "name_format"
CONF_UPDATE_INTERVAL: Final = "update_interval_hours"

DEFAULT_URL: Final = "https://sync.infomaniak.com/"
DEFAULT_UPDATE_INTERVAL: Final = 24
DEFAULT_SHOW_AGE: Final = True

# Ordre d'affichage du nom : "Prénom Nom", "Nom Prénom", ou le champ FN tel quel.
NAME_FORMAT_GIVEN_FAMILY: Final = "given_family"
NAME_FORMAT_FAMILY_GIVEN: Final = "family_given"
NAME_FORMAT_FN: Final = "fn"
NAME_FORMATS: Final = [
    NAME_FORMAT_GIVEN_FAMILY,
    NAME_FORMAT_FAMILY_GIVEN,
    NAME_FORMAT_FN,
]
DEFAULT_NAME_FORMAT: Final = NAME_FORMAT_GIVEN_FAMILY

# Fenêtre maximale explorée pour trouver le prochain anniversaire.
LOOKAHEAD_DAYS: Final = 400

# Catégorie de traduction personnalisée (clés "event" de translations/<lang>.json).
TRANSLATION_CATEGORY: Final = "event"
