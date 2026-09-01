# CardDAV Birthdays

A Home Assistant custom integration that syncs a **CardDAV** address book
(Infomaniak kSuite, Nextcloud, Radicale, Baïkal, iCloud…) and exposes your contacts'
birthdays as a **native calendar entity** — no Remote Calendar and no intermediate
`.ics` file required.

- A single entity: `calendar.birthdays`
- All-day events, expanded across every year (past and future)
- Age shown in the title when the vCard carries a birth year, in Home Assistant's language:
  `Paul Lefebvre (39)` in English, `Paul Lefebvre (39 ans)` in French
- Configurable sync interval: every 24 h by default, 168 h for once a week
- Read-only; nothing leaves your network except the calls to your own CardDAV server

## Installation

### Through HACS (custom repository)

1. HACS → ⋮ menu → **Custom repositories**
2. Paste `https://github.com/<you>/homeassistant-carddav-birthdays`, category **Integration**
3. Install "CardDAV Birthdays", then restart Home Assistant

### Manually

Copy `custom_components/carddav_birthdays/` into `config/custom_components/`, then restart.

## Configuration

**Settings → Devices & services → Add integration → CardDAV Birthdays**

### Infomaniak (kSuite)

| Field | Value |
|---|---|
| Server URL | `https://sync.infomaniak.com/` |
| Username | the username given by the sync assistant, **in uppercase** (e.g. `AB12345`) |
| Password | an **application password** created at [config.infomaniak.com](https://config.infomaniak.com) (required when 2FA is enabled) |

The integration then discovers the account's address books automatically
(`current-user-principal` → `addressbook-home-set`) and lets you pick the ones to watch.

### Other servers

Same idea: the server's base URL (or an address book URL directly), username and password.
The client uses `addressbook-query` (RFC 6352) and automatically falls back to
`PROPFIND` + `GET` on servers that reject the REPORT.

### Options

From the integration's **Configure** button:

- **Sync interval** in hours (24 = daily, 168 = weekly)
- **Show age** in the event title

## Usage

Drop the entity onto a **Calendar** card as-is. Its state is `on` on a birthday.

Morning notification:

```yaml
automation:
  - alias: Today's birthdays
    triggers:
      - trigger: time
        at: "08:00:00"
    actions:
      - action: calendar.get_events
        target:
          entity_id: calendar.birthdays
        data:
          duration:
            hours: 24
        response_variable: agenda
      - condition: template
        value_template: "{{ agenda['calendar.birthdays'].events | count > 0 }}"
      - action: notify.persistent_notification
        data:
          title: Birthdays
          message: >-
            {{ agenda['calendar.birthdays'].events
               | map(attribute='summary') | join(', ') }}
```

## Supported vCard fields

`BDAY` in the forms `1987-04-12`, `19870412`, `--0412`, `--04-12`, with or without a time part.
Apple's placeholder years (`1604`, `X-APPLE-OMIT-YEAR`) are treated as "year unknown".
The display name comes from `FN`, falling back to `N` (given name + family name).
Quoted-printable values from vCard 2.1 are decoded.
February 29 is shown on February 28 in non-leap years.

## Localisation

Event titles and descriptions come from the `event` section of
`custom_components/carddav_birthdays/translations/<lang>.json`, resolved against
Home Assistant's configured language (falling back to English):

```json
"event": {
  "with_age": "{name} ({age})",
  "with_age_one": "{name} ({age})",
  "description": "Birthday",
  "description_with_date": "Birthday — born on {date}",
  "date_format": "%Y-%m-%d"
}
```

English and French ship with the integration. To add a language, copy `en.json`
to `<lang>.json` and translate it — `with_age_one` covers languages that need a
singular form, and `date_format` is a `strftime` pattern.

## Tests

```bash
python3 tests/test_parser.py    # vCard parser
python3 tests/test_client.py    # CardDAV client against a fake server
python3 tests/test_calendar.py  # occurrence expansion and event titles
```

A French version of this document is available in [README.fr.md](README.fr.md).

## License

MIT
