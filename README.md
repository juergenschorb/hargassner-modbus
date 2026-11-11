# Hargassner Modbus

Home-Assistant-Integration für Hargassner-Pelletkessel (z. B. Nano-PK) über die Modbus-TCP-Schnittstelle der **Hargassner-Loxone-Erweiterung**. Home Assistant übernimmt dabei die Rolle des Loxone Miniservers: Werte lesen, Lebenszeichen senden und auf Wunsch die Vorlauftemperatur von Heizkreis 2 vorgeben.

Registerbelegung laut Hargassner-Anleitung „Zubehör Loxone“ V01.

## Funktionen

- Einrichtung komplett über die Oberfläche (IP, Port, Geräteadresse, Kesseltyp)
- Lebenszeichen (Register 6499) alle 10 s, Messwerte alle 30 s
- Temperaturen: Außen (aktuell/gemittelt), Kessel Ist/Soll, Rauchgas, Rücklauf, Vorlauf HK1 und HK2 Ist/Soll
- Zustände als Text: Kesselzustand (z. B. „Leistungsbrand“), Zustand HK1 und HK2 (z. B. „Restwärme“)
- Leistung, Lagerstand, Störungsnummer und „Störung“ als Ja/Nein
- „Restwärme HK1/HK2“ als Ja/Nein, z. B. um Heizkörperventile offen zu halten
- Optional Puffer oben/Mitte/unten und Boiler
- **HK2 vorgeben**: Schalter und Sollwert. Nur wenn der Schalter an ist, schreibt Home Assistant die Vorlauftemperatur HK2 (Register 6999) alle 60 s und bei jeder Änderung. Nach der Einrichtung ist er **aus**.
- Die Register für den Vorlauf-Soll lassen sich je Heizkreis unter *Konfigurieren* ändern (Standard laut Anleitung V01: HK1 6998, HK2 6999).
- **HK1 vorgeben**: genauso für HK1 (Register 6998), eigener Schalter, ebenfalls **aus**. Beide Heizkreise sind unabhängig voneinander.

> **HK1/HK2 vorgeben** wirkt nur, wenn der Heizkreis am Kessel auf „Loxone“ (externe Vorgabe) steht. Dann gilt die Heizkurve des Kessels für diesen Heizkreis nicht mehr: Home Assistant muss die Vorlauftemperatur selbst passend zur Außentemperatur vorgeben. Was der Kessel macht, wenn Home Assistant ausfällt (Lebenszeichen bleibt aus), bitte im Kesselmenü bzw. in der Hargassner-Anleitung zur Loxone-Schnittstelle prüfen.
- **Vorlauf berechnen (Automatik)**: Heizkurve nach Außentemperatur plus Anhebung/Absenkung nach Raumbedarf, siehe unten
- Fällt die Verbindung weg, werden die Werte „nicht verfügbar“ und die Integration verbindet sich selbst neu
- Eigener schlanker Modbus-Client, keine Abhängigkeit von pymodbus

## Installation

### Über HACS

1. HACS → ⋮ → **Benutzerdefinierte Repositories**
2. URL `https://github.com/juergenschorb/hargassner-modbus`, Typ **Integration** → Hinzufügen
3. „Hargassner Modbus“ suchen → Herunterladen
4. Home Assistant neu starten

### Manuell

Ordner `custom_components/hargassner_modbus` nach `/config/custom_components/` kopieren und Home Assistant neu starten.

## Einrichten

*Einstellungen → Geräte & Dienste → Integration hinzufügen → Hargassner Modbus*

| Feld | Wert |
| --- | --- |
| IP-Adresse | IP des Kessels (oder des modbus-proxy, wenn der Kessel nur eine Verbindung annimmt) |
| Port | 502 |
| Geräteadresse | 1 |
| Kesseltyp | Nano-PK / HSV / CL oder Eco-PK / Eco-HK / WTH-Touch (für die Texte des Kesselzustands) |

Beim Einrichten liest die Integration Lebenszeichen, Außen- und Kesseltemperatur und erkennt daraus die Wortreihenfolge der Kommazahlen selbst.

Unter **Konfigurieren** gibt es drei Bereiche:

- **Allgemein und Raumbedarf:** Kesseltyp, Puffer und Boiler abfragen, Wortreihenfolge, Heizgrenze und Stärke der Raumkorrektur.
- **Heizkreis 1 / Heizkreis 2:** Mindest- und Höchstwert für den Vorlauf (Standard 20–60 °C, darüber wird nie geschrieben), die **Räume** (Thermostate) dieses Heizkreises und die Heizkurve. Räume lassen sich jederzeit hinzufügen oder entfernen.

## Vorlauf berechnen

Je Heizkreis gibt es den Sensor **„Vorlauf HKx berechnet“** und den Schalter **„HKx Automatik“**.

1. **Heizkurve:** Zwei Punkte, z. B. −10 °C außen → 50 °C Vorlauf und +15 °C außen → 28 °C Vorlauf. Dazwischen wird gerade gerechnet, außerhalb verlängert. Als Außentemperatur dient die **gemittelte** Außentemperatur des Kessels.
2. **Raumbedarf:** Aus den ausgewählten Thermostaten (z. B. Versatile Thermostat, Better Thermostat) zählt der Raum mit der größten Lücke Soll − Ist. Thermostate, die aus oder nicht verfügbar sind, zählen nicht.
   - Raum zu kalt: Vorlauf + (Lücke × „Anhebung je K“, Standard 3), höchstens „Anhebung höchstens“ (10 K).
   - Alle Räume über Soll: Vorlauf entsprechend tiefer, höchstens „Absenkung höchstens“ (5 K).
   - Abweichungen bis 0,2 K werden ignoriert.
3. **Heizgrenze:** Ab der eingestellten gemittelten Außentemperatur (Standard 18 °C) gilt nur noch der Mindest-Vorlauf.
4. Das Ergebnis wird auf ganze Grad gerundet und auf Mindest-/Höchstwert begrenzt.

Die Attribute des Sensors zeigen Außentemperatur, Kurvenwert, Korrektur, maßgeblichen Raum und Grund, z. B. „EG Bad 1,2 K zu kalt“.

**Senden:** Ist „HKx Automatik“ an, wird der berechnete Wert statt „Vorlauf HKx Vorgabe“ gesendet, aber nur wenn auch **„HKx vorgeben“** an ist. Tipp: Erst nur den Sensor beobachten und mit dem Kesselwert vergleichen, dann einschalten.

## Fehlersuche

- Beim Einrichten steht der genaue Grund hinter „Details:“ und im Protokoll (*Einstellungen → System → Protokolle*, Suche „Hargassner“). Zeigt das Formular noch alte Texte, den Browser-Zwischenspeicher leeren.
- Läuft der modbus-proxy als Add-on auf demselben Home Assistant, als IP-Adresse den **Hostnamen des Add-ons** (steht auf der Infoseite des Add-ons) und den Port aus der Add-on-Konfiguration eintragen. Die HA-IP oder `localhost` gehen nur, wenn der Port unter „Netzwerk“ freigegeben ist.
- Antwortet die eingegebene Geräteadresse nicht, probiert die Integration selbst 1, 0 und 255.
- Für die gesendeten und empfangenen Modbus-Bytes in `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.hargassner_modbus: debug
```

## Umstellen von Loxone

1. **Lesen:** Integration einrichten, „HK2 vorgeben“ bleibt aus. Werte mit dem Kesseldisplay vergleichen. Loxone regelt weiter.
2. **Backup:** Home Assistant (bzw. Snapshot der VM) und die Loxone-Config sichern.
3. **Umschalten:** In der Loxone Config den Aktor „Solltemperatur HK2“ (6999) und den Abruf von 6499 deaktivieren und in den Miniserver speichern. Dann **„Vorlauf HK2 Vorgabe“** setzen und **„HK2 vorgeben“** einschalten, innerhalb von 60 s.
4. **Beobachten:** Die HK2-Solltemperatur am Kessel folgt der Vorgabe, es kommt keine Lebenszeichen-Störung.
5. **Zurück:** „HK2 vorgeben“ aus, Loxone-Objekte wieder aktivieren.
6. **HK1 (optional):** Später genauso mit „Solltemperatur HK1“ (6998) und **„HK1 vorgeben“**. Vorher am Kessel prüfen, dass HK1 auf „Loxone“ steht.

**Nie Loxone und Home Assistant gleichzeitig schreiben lassen.**

Die Vorgabe lässt sich von Automationen setzen, z. B. aus einer Heizkurve:

```yaml
action: number.set_value
target:
  entity_id: number.hargassner_vorlauf_hk2_vorgabe
data:
  value: 42
```

## Hinweise

- Die Solltemperatur wird in ganzen Grad geschrieben (uint16, wie in der Anleitung).
- Ob Störungsnummer 0 wirklich „keine Störung“ heißt, sagt die Anleitung nicht. Bitte beobachten.
- Die Einheit des Lagerstands ist in der Anleitung nicht angegeben, daher ohne Einheit.

## Tests

Getestet mit einem nachgebauten Kessel (Modbus-TCP-Server in `tests/fake_boiler.py`), nicht mit einem echten Kessel:

```bash
pip install -r requirements_test.txt
pytest
```

## Stand

Version 0.3.2.
