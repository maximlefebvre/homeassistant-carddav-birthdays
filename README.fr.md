# CardDAV Birthdays to Calendar

Intégration personnalisée Home Assistant qui synchronise un carnet d'adresses **CardDAV**
(Infomaniak kSuite, Nextcloud, Radicale, Baïkal, iCloud…) et expose les anniversaires
des contacts sous forme d'**entité calendrier native** — pas besoin de Remote Calendar
ni de fichier `.ics` intermédiaire.

- Une seule entité : `calendar.anniversaires`
- Événements journée entière, développés sur toutes les années (passées et futures)
- Âge affiché dans le titre quand la vCard contient l'année de naissance, dans la langue
  de Home Assistant : `Paul Lefebvre (39 ans)` en français, `Paul Lefebvre (39)` en anglais
- Synchronisation configurable : toutes les 24 h par défaut, 168 h pour une fois par semaine
- Lecture seule, aucune donnée envoyée ailleurs que vers votre serveur CardDAV

## Installation

### Via HACS (dépôt personnalisé)

1. HACS → menu ⋮ → **Dépôts personnalisés**
2. URL `https://github.com/<vous>/homeassistant-carddav-birthdays`, catégorie **Integration**
3. Installer « CardDAV Birthdays », puis redémarrer Home Assistant

### Manuellement

Copier `custom_components/carddav_birthdays/` dans `config/custom_components/`, puis redémarrer.

## Configuration

**Paramètres → Appareils et services → Ajouter une intégration → CardDAV Birthdays**

### Infomaniak (kSuite)

| Champ | Valeur |
|---|---|
| URL du serveur | `https://sync.infomaniak.com/` |
| Identifiant | l'identifiant fourni par l'assistant de synchronisation, **en majuscules** (ex. `AB12345`) |
| Mot de passe | un **mot de passe d'application** créé sur [config.infomaniak.com](https://config.infomaniak.com) (obligatoire si la 2FA est active) |

L'intégration découvre ensuite automatiquement les carnets d'adresses du compte
(`current-user-principal` → `addressbook-home-set`) et vous laisse choisir ceux à surveiller.

### Autres serveurs

Même principe : URL de base du serveur (ou directement celle d'un carnet), identifiant, mot de passe.
Le client utilise `addressbook-query` (RFC 6352) et retombe automatiquement sur
`PROPFIND` + `GET` pour les serveurs qui refusent le REPORT.

### Options

Bouton **Configurer** de l'intégration :

- **Fréquence de synchronisation** en heures (24 = quotidien, 168 = hebdomadaire)
- **Afficher l'âge** dans le titre de l'événement

## Utilisation

L'entité s'ajoute telle quelle à la carte **Calendrier**. Son état est `on` le jour d'un anniversaire.

Notification le matin même :

```yaml
automation:
  - alias: Anniversaires du jour
    triggers:
      - trigger: time
        at: "08:00:00"
    actions:
      - action: calendar.get_events
        target:
          entity_id: calendar.anniversaires
        data:
          duration:
            hours: 24
        response_variable: agenda
      - condition: template
        value_template: "{{ agenda['calendar.anniversaires'].events | count > 0 }}"
      - action: notify.persistent_notification
        data:
          title: Anniversaires
          message: >-
            {{ agenda['calendar.anniversaires'].events
               | map(attribute='summary') | join(', ') }}
```

## Champs vCard reconnus

`BDAY` sous les formes `1987-04-12`, `19870412`, `--0412`, `--04-12`, avec ou sans heure.
Les années « fantômes » d'Apple (`1604`, `X-APPLE-OMIT-YEAR`) sont traitées comme « année inconnue ».
Le nom vient de `FN`, ou à défaut de `N` (prénom + nom). Le quoted-printable des vCards 2.1 est décodé.
Un 29 février est affiché le 28 février les années non bissextiles.

## Localisation

Les titres et descriptions d'événements viennent de la section `event` de
`custom_components/carddav_birthdays/translations/<lang>.json`, résolue selon la langue
configurée dans Home Assistant (repli sur l'anglais) :

```json
"event": {
  "with_age": "{name} ({age} ans)",
  "with_age_one": "{name} ({age} an)",
  "description": "Anniversaire",
  "description_with_date": "Anniversaire — né(e) le {date}",
  "date_format": "%d/%m/%Y"
}
```

Le français et l'anglais sont fournis. Pour ajouter une langue, copier `fr.json` en
`<lang>.json` et traduire : `with_age_one` gère le singulier et `date_format` est un
motif `strftime`.

## Tests

```bash
python3 tests/test_parser.py    # parseur vCard
python3 tests/test_client.py    # client CardDAV contre un faux serveur
python3 tests/test_calendar.py  # expansion des occurrences et titres
```

## Licence

MIT
