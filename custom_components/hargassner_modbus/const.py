"""Konstanten und Registerbelegung (Hargassner-Anleitung „Zubehör Loxone“ V01)."""

from __future__ import annotations

from dataclasses import dataclass

DOMAIN = "hargassner_modbus"

CONF_UNIT = "unit"
CONF_WORD_SWAP = "word_swap"
CONF_BOILER_TYPE = "boiler_type"
CONF_HK2_MIN = "hk2_min"
CONF_HK2_MAX = "hk2_max"
CONF_EXTRAS = "extras"

DEFAULT_PORT = 502
DEFAULT_UNIT = 1
DEFAULT_HK2_MIN = 20
DEFAULT_HK2_MAX = 60

# Lebenszeichen: muss alle 10 s gelesen werden (sonst Störung nach Kesselparameter Z1b)
REG_KEEPALIVE = 6499
KEEPALIVE_INTERVAL = 10  # s
VALUES_EVERY = 3  # Messwerte bei jedem 3. Lebenszeichen lesen, also alle 30 s
# Solltemperatur HK2 (EG): uint16, FC16, zyklisch alle 60 s wie Loxone
REG_HK2_SETPOINT = 6999
WRITE_INTERVAL = 60  # s

BOILER_NANO = "nano"  # HSV / CL / Nano-PK
BOILER_ECO = "eco"  # Eco-HK / Eco-PK / WTH-Touch

BOILER_STATES = {
    BOILER_NANO: {
        0: "Init", 1: "Aus", 2: "Schieberost Init", 3: "Start", 4: "Zündung Einschub",
        5: "Zündung Pause", 6: "Zündung reduziert", 7: "Leistungsbrand", 8: "Gluterhaltung",
        9: "Entaschung", 10: "Entaschung Rost", 11: "Entaschung Nachlauf", 12: "Reinigung",
        13: "Füllen Start", 14: "Füllen", 15: "Hand",
    },
    BOILER_ECO: {
        0: "Init", 1: "Aus", 3: "Zündprobe", 4: "Zündung", 5: "Leistungsbrand",
        6: "Gluterhaltung", 7: "Ausbrand", 9: "Entaschung", 10: "STB", 11: "Hand",
        12: "Stückholz-Notbetrieb",
    },
}

HK_STATES = {
    0: "Aus", 1: "Heizen", 2: "Absenken Rampe", 3: "Absenken", 4: "Tag-Nacht-Abschaltung",
    5: "Sommerabschaltung", 6: "Frostschutz", 7: "Estrich", 8: "Hand", 9: "Restwärme",
    10: "Sommerbadheizen",
}


@dataclass(frozen=True)
class Reg:
    """Ein float32-Leseregister."""

    key: str
    address: int
    kind: str = "temp"  # temp | percent | code | number
    extra: bool = False  # nur mit Option „Puffer/Boiler“ abfragen
    precision: int = 1


READ_REGISTERS: tuple[Reg, ...] = (
    Reg("aussen", 8),
    Reg("aussen_gemittelt", 6),
    Reg("kessel_ist", 82),
    Reg("kessel_soll", 84),
    Reg("kesselzustand", 86, "code"),
    Reg("leistung", 88, "percent", precision=0),
    Reg("rauchgas", 126, precision=0),
    Reg("ruecklauf", 130),
    Reg("hk1_vorlauf_ist", 144),
    Reg("hk1_vorlauf_soll", 146),
    Reg("hk1_zustand", 178, "code"),
    Reg("hk2_vorlauf_ist", 148),
    Reg("hk2_vorlauf_soll", 150),
    Reg("hk2_zustand", 180, "code"),
    Reg("lagerstand", 220, "number", precision=0),
    Reg("stoerung", 222, "code"),
    Reg("puffer_oben", 122, extra=True),
    Reg("puffer_mitte", 254, extra=True),
    Reg("puffer_unten", 124, extra=True),
    Reg("boiler_temp", 10, extra=True),
    Reg("boiler_zustand", 190, "code", extra=True),
)
