"""Client CardDAV minimaliste et parseur vCard (FN / N / BDAY)."""

from __future__ import annotations

import hashlib
import logging
import quopri
import re
from dataclasses import dataclass
from datetime import date
from xml.etree import ElementTree as ET

import aiohttp
from yarl import URL

_LOGGER = logging.getLogger(__name__)

DAV_NS = "DAV:"
CARDDAV_NS = "urn:ietf:params:xml:ns:carddav"
USER_AGENT = "Home Assistant CardDAV Birthdays"
TIMEOUT = aiohttp.ClientTimeout(total=60)

_PROPFIND_PRINCIPAL = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<d:propfind xmlns:d="DAV:"><d:prop><d:current-user-principal/>'
    "</d:prop></d:propfind>"
)
_PROPFIND_HOME_SET = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:carddav">'
    "<d:prop><c:addressbook-home-set/></d:prop></d:propfind>"
)
_PROPFIND_COLLECTIONS = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/><d:displayname/>'
    "</d:prop></d:propfind>"
)
_REPORT_ADDRESSBOOK = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<c:addressbook-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:carddav">'
    "<d:prop><d:getetag/><c:address-data>"
    '<c:prop name="VERSION"/><c:prop name="UID"/><c:prop name="FN"/>'
    '<c:prop name="N"/><c:prop name="BDAY"/>'
    "</c:address-data></d:prop><c:filter/></c:addressbook-query>"
)
_PROPFIND_CARDS = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<d:propfind xmlns:d="DAV:"><d:prop><d:getcontenttype/></d:prop></d:propfind>'
)


class CardDavError(Exception):
    """Erreur de communication avec le serveur CardDAV."""


class CardDavAuthError(CardDavError):
    """Identifiants refusés par le serveur."""


@dataclass(frozen=True, slots=True)
class AddressBook:
    """Un carnet d'adresses découvert sur le serveur."""

    url: str
    name: str


@dataclass(frozen=True, slots=True)
class Birthday:
    """Un anniversaire extrait d'une vCard.

    `name` reprend le champ FN tel quel ; `given` et `family` viennent du champ
    structuré N et permettent de recomposer le nom dans l'ordre souhaité.
    """

    uid: str
    name: str
    month: int
    day: int
    year: int | None = None
    given: str = ""
    family: str = ""

    def occurrence(self, year: int) -> date:
        """Date de l'anniversaire pour une année donnée (29/02 -> 28/02)."""
        try:
            return date(year, self.month, self.day)
        except ValueError:
            return date(year, 2, 28)

    def age_at(self, year: int) -> int | None:
        """Âge atteint lors de l'occurrence de cette année."""
        if self.year is None:
            return None
        return year - self.year


class CardDavClient:
    """Client CardDAV en lecture seule, suffisant pour lister les anniversaires."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        url: str,
        username: str,
        password: str,
    ) -> None:
        """Initialiser le client."""
        self._session = session
        self._url = url if url.endswith("/") else f"{url}/"
        self._auth = aiohttp.BasicAuth(username, password)

    async def _dav(
        self,
        method: str,
        url: str,
        body: str | None = None,
        depth: str | None = "0",
        accept_xml: bool = True,
    ) -> tuple[str, URL]:
        """Exécuter une requête WebDAV et renvoyer (corps, URL finale)."""
        headers = {"User-Agent": USER_AGENT}
        if body is not None:
            headers["Content-Type"] = "application/xml; charset=utf-8"
        if depth is not None:
            headers["Depth"] = depth
        try:
            async with self._session.request(
                method,
                url,
                data=body.encode("utf-8") if body is not None else None,
                headers=headers,
                auth=self._auth,
                timeout=TIMEOUT,
            ) as response:
                if response.status in (401, 403):
                    raise CardDavAuthError(
                        f"Authentification refusée (HTTP {response.status})"
                    )
                text = await response.text()
                if response.status >= 400:
                    raise CardDavError(f"{method} {url} : HTTP {response.status}")
                return text, response.url
        except aiohttp.ClientError as err:
            raise CardDavError(f"{method} {url} : {err}") from err

    async def _dav_xml(
        self, method: str, url: str, body: str, depth: str | None = "0"
    ) -> tuple[ET.Element, URL]:
        """Exécuter une requête WebDAV et parser la réponse XML."""
        text, final_url = await self._dav(method, url, body, depth)
        try:
            return ET.fromstring(text), final_url
        except ET.ParseError as err:
            raise CardDavError(f"Réponse XML invalide depuis {url}") from err

    @staticmethod
    def _hrefs(root: ET.Element, base: URL, *path: str) -> list[str]:
        """Extraire les href absolus sous un chemin de propriétés donné."""
        found: list[str] = []
        for response in root.iter(f"{{{DAV_NS}}}response"):
            for prop in response.iter(f"{{{DAV_NS}}}prop"):
                node: ET.Element | None = prop
                for step_ns, step_tag in (p.split("|") for p in path):
                    if node is None:
                        break
                    node = node.find(f"{{{step_ns}}}{step_tag}")
                if node is None:
                    continue
                for href in node.iter(f"{{{DAV_NS}}}href"):
                    if href.text:
                        found.append(str(base.join(URL(href.text.strip()))))
        return found

    async def async_discover_addressbooks(self) -> list[AddressBook]:
        """Découvrir les carnets d'adresses du compte."""
        home_urls: list[str] = []
        for candidate in (self._url, f"{self._url}.well-known/carddav"):
            try:
                root, final_url = await self._dav_xml(
                    "PROPFIND", candidate, _PROPFIND_PRINCIPAL
                )
            except CardDavAuthError:
                raise
            except CardDavError as err:
                _LOGGER.debug("Découverte du principal impossible sur %s : %s", candidate, err)
                continue
            for principal in self._hrefs(root, final_url, f"{DAV_NS}|current-user-principal"):
                try:
                    home_root, home_base = await self._dav_xml(
                        "PROPFIND", principal, _PROPFIND_HOME_SET
                    )
                except CardDavError as err:
                    _LOGGER.debug("addressbook-home-set illisible sur %s : %s", principal, err)
                    continue
                home_urls.extend(
                    self._hrefs(home_root, home_base, f"{CARDDAV_NS}|addressbook-home-set")
                )
            if home_urls:
                break

        # Repli : l'URL fournie est peut-être déjà le home-set ou un carnet.
        if not home_urls:
            home_urls = [self._url]

        addressbooks: dict[str, AddressBook] = {}
        for home in home_urls:
            root, base = await self._dav_xml(
                "PROPFIND", home, _PROPFIND_COLLECTIONS, depth="1"
            )
            for response in root.iter(f"{{{DAV_NS}}}response"):
                href_node = response.find(f"{{{DAV_NS}}}href")
                if href_node is None or not href_node.text:
                    continue
                resourcetype = response.find(
                    f".//{{{DAV_NS}}}prop/{{{DAV_NS}}}resourcetype"
                )
                if resourcetype is None:
                    continue
                if resourcetype.find(f"{{{CARDDAV_NS}}}addressbook") is None:
                    continue
                url = str(base.join(URL(href_node.text.strip())))
                display = response.find(f".//{{{DAV_NS}}}prop/{{{DAV_NS}}}displayname")
                name = (display.text or "").strip() if display is not None else ""
                addressbooks[url] = AddressBook(url=url, name=name or url.rstrip("/").rsplit("/", 1)[-1])

        if not addressbooks:
            raise CardDavError("Aucun carnet d'adresses trouvé sur ce serveur")
        return sorted(addressbooks.values(), key=lambda book: book.name.lower())

    async def async_fetch_vcards(self, addressbook_url: str) -> list[str]:
        """Récupérer toutes les vCards d'un carnet d'adresses."""
        try:
            root, _ = await self._dav_xml(
                "REPORT", addressbook_url, _REPORT_ADDRESSBOOK, depth="1"
            )
        except CardDavAuthError:
            raise
        except CardDavError as err:
            _LOGGER.debug(
                "addressbook-query refusé sur %s (%s), repli sur PROPFIND+GET",
                addressbook_url,
                err,
            )
            return await self._async_fetch_vcards_fallback(addressbook_url)

        cards = [
            node.text
            for node in root.iter(f"{{{CARDDAV_NS}}}address-data")
            if node.text and "BEGIN:VCARD" in node.text
        ]
        if cards:
            return cards
        return await self._async_fetch_vcards_fallback(addressbook_url)

    async def _async_fetch_vcards_fallback(self, addressbook_url: str) -> list[str]:
        """Lister puis télécharger les vCards une par une."""
        root, base = await self._dav_xml(
            "PROPFIND", addressbook_url, _PROPFIND_CARDS, depth="1"
        )
        urls = []
        for href in root.iter(f"{{{DAV_NS}}}href"):
            if href.text and href.text.strip().lower().endswith(".vcf"):
                urls.append(str(base.join(URL(href.text.strip()))))

        cards: list[str] = []
        for url in urls:
            try:
                text, _ = await self._dav("GET", url, depth=None)
            except CardDavError as err:
                _LOGGER.debug("vCard illisible %s : %s", url, err)
                continue
            if "BEGIN:VCARD" in text:
                cards.append(text)
        return cards

    async def async_fetch_birthdays(self, addressbook_urls: list[str]) -> list[Birthday]:
        """Récupérer et parser les anniversaires de plusieurs carnets."""
        birthdays: dict[str, Birthday] = {}
        for url in addressbook_urls:
            for raw in await self.async_fetch_vcards(url):
                for card in split_vcards(raw):
                    birthday = parse_vcard(card)
                    if birthday is not None:
                        birthdays[birthday.uid] = birthday
        return sorted(birthdays.values(), key=lambda item: (item.month, item.day, item.name))


# --------------------------------------------------------------------------- #
# Parseur vCard
# --------------------------------------------------------------------------- #

_UNFOLD_RE = re.compile(r"\r?\n[ \t]")
_DATE_FULL_RE = re.compile(r"^(\d{4})-?(\d{2})-?(\d{2})")
_DATE_NOYEAR_RE = re.compile(r"^-{1,2}(\d{2})-?(\d{2})")
_OMIT_YEARS = {0, 1604}


def split_vcards(raw: str) -> list[str]:
    """Découper un flux pouvant contenir plusieurs vCards."""
    cards: list[str] = []
    current: list[str] = []
    for line in raw.splitlines():
        if line.strip().upper().startswith("BEGIN:VCARD"):
            current = [line]
        elif current:
            current.append(line)
            if line.strip().upper().startswith("END:VCARD"):
                cards.append("\n".join(current))
                current = []
    return cards or ([raw] if "BEGIN:VCARD" in raw else [])


def _split_property(line: str) -> tuple[str, str] | None:
    """Séparer 'NOM;PARAMS' et la valeur, en respectant les guillemets."""
    in_quotes = False
    for index, char in enumerate(line):
        if char == '"':
            in_quotes = not in_quotes
        elif char == ":" and not in_quotes:
            return line[:index], line[index + 1 :]
    return None


def _split_unescaped(value: str, separator: str) -> list[str]:
    """Découper une valeur vCard sur un séparateur non échappé."""
    parts: list[str] = []
    buffer: list[str] = []
    escaped = False
    for char in value:
        if escaped:
            buffer.append("\\" + char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == separator:
            parts.append("".join(buffer))
            buffer = []
        else:
            buffer.append(char)
    if escaped:
        buffer.append("\\")
    parts.append("".join(buffer))
    return parts


def _unescape(value: str) -> str:
    """Retirer les échappements vCard."""
    out: list[str] = []
    escaped = False
    for char in value:
        if escaped:
            out.append({"n": "\n", "N": "\n"}.get(char, char))
            escaped = False
        elif char == "\\":
            escaped = True
        else:
            out.append(char)
    return "".join(out).strip()


def _parse_params(raw_params: list[str]) -> dict[str, str]:
    """Parser les paramètres d'une propriété vCard."""
    params: dict[str, str] = {}
    for item in raw_params:
        if "=" in item:
            key, _, value = item.partition("=")
            params[key.strip().upper()] = value.strip().strip('"')
        elif item.strip():
            params.setdefault("TYPE", item.strip().upper())
            params[item.strip().upper()] = ""
    return params


def _decode_value(value: str, params: dict[str, str]) -> str:
    """Décoder un éventuel quoted-printable (vCard 2.1)."""
    if params.get("ENCODING", "").upper() != "QUOTED-PRINTABLE" and (
        "QUOTED-PRINTABLE" not in params
    ):
        return value
    charset = params.get("CHARSET", "utf-8")
    try:
        return quopri.decodestring(value.encode("utf-8")).decode(charset, "replace")
    except (LookupError, ValueError):
        return value


def parse_birthday_value(value: str, params: dict[str, str]) -> tuple[int, int, int | None] | None:
    """Parser une valeur BDAY et renvoyer (mois, jour, année|None)."""
    value = value.strip()
    if not value:
        return None

    year: int | None = None
    match = _DATE_FULL_RE.match(value)
    if match:
        year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
        if year in _OMIT_YEARS or params.get("X-APPLE-OMIT-YEAR"):
            year = None
    else:
        match = _DATE_NOYEAR_RE.match(value)
        if not match:
            return None
        month, day = int(match.group(1)), int(match.group(2))

    if not 1 <= month <= 12 or not 1 <= day <= 31:
        return None
    try:
        date(year or 2020, month, day)
    except ValueError:
        return None
    if year is not None and not 1900 <= year <= date.today().year:
        year = None
    return month, day, year


def parse_vcard(raw: str) -> Birthday | None:
    """Extraire un anniversaire d'une vCard, ou None s'il n'y en a pas."""
    text = _UNFOLD_RE.sub("", raw.replace("\r\n", "\n"))
    fields: dict[str, tuple[str, dict[str, str]]] = {}

    for line in text.split("\n"):
        if not line.strip():
            continue
        split = _split_property(line)
        if split is None:
            continue
        name_part, value = split
        segments = _split_unescaped(name_part, ";")
        prop = segments[0].split(".")[-1].strip().upper()
        if prop not in ("FN", "N", "BDAY", "UID"):
            continue
        params = _parse_params(segments[1:])
        fields[prop] = (_decode_value(value, params), params)

    if "BDAY" not in fields:
        return None
    parsed = parse_birthday_value(*fields["BDAY"])
    if parsed is None:
        return None
    month, day, year = parsed

    given = family = ""
    if "N" in fields:
        parts = [_unescape(part) for part in _split_unescaped(fields["N"][0], ";")]
        family = parts[0] if parts else ""
        given = parts[1] if len(parts) > 1 else ""

    name = _unescape(fields["FN"][0]) if "FN" in fields else ""
    if not name:
        name = " ".join(part for part in (given, family) if part)
    if not name:
        return None

    uid = _unescape(fields["UID"][0]) if "UID" in fields else ""
    if not uid:
        uid = hashlib.sha1(f"{name}-{year}-{month}-{day}".encode()).hexdigest()

    return Birthday(
        uid=uid,
        name=name,
        month=month,
        day=day,
        year=year,
        given=given,
        family=family,
    )
