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

Unter **Konfigurieren** lassen sich ändern: Kesseltyp, Mindest- und Höchstwert für den Vorlauf HK2 (Standard 20–60 °C, darüber wird nie geschrieben), Puffer und Boiler abfragen, Wortreihenfolge.

## Umstellen von Loxone

1. **Lesen:** Integration einrichten, „HK2 vorgeben“ bleibt aus. Werte mit dem Kesseldisplay vergleichen. Loxone regelt weiter.
2. **Backup:** Home Assistant (bzw. Snapshot der VM) und die Loxone-Config sichern.
3. **Umschalten:** In der Loxone Config den Aktor „Solltemperatur HK2“ (6999) und den Abruf von 6499 deaktivieren und in den Miniserver speichern. Dann **„Vorlauf HK2 Vorgabe“** setzen und **„HK2 vorgeben“** einschalten, innerhalb von 60 s.
4. **Beobachten:** Die HK2-Solltemperatur am Kessel folgt der Vorgabe, es kommt keine Lebenszeichen-Störung.
5. **Zurück:** „HK2 vorgeben“ aus, Loxone-Objekte wieder aktivieren.

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

Version 0.1.0.
