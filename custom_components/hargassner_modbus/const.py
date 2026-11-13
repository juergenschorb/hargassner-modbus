"""Konstanten und Registerbelegung (Hargassner-Anleitung „Zubehör Loxone“ V01)."""

from __future__ import annotations

from dataclasses import dataclass

DOMAIN = "hargassner_modbus"

CONF_UNIT = "unit"
CONF_WORD_SWAP = "word_swap"
CONF_BOILER_TYPE = "boiler_type"
CONF_HK1_MIN = "hk1_min"
CONF_HK1_MAX = "hk1_max"
CONF_HK2_MIN = "hk2_min"
CONF_HK2_MAX = "hk2_max"
CONF_EXTRAS = "extras"

DEFAULT_PORT = 502
DEFAULT_UNIT = 1
DEFAULT_HK_MIN = 20
DEFAULT_HK_MAX = 60
DEFAULT_HK2_MIN = DEFAULT_HK_MIN
DEFAULT_HK2_MAX = DEFAULT_HK_MAX

# Lebenszeichen: muss alle 10 s gelesen werden (sonst Störung nach Kesselparameter Z1b)
REG_KEEPALIVE = 6499
KEEPALIVE_INTERVAL = 10  # s
VALUES_EVERY = 3  # Messwerte bei jedem 3. Lebenszeichen lesen, also alle 30 s
# Solltemperatur HK1/HK2: uint16, FC16, zyklisch alle 60 s wie Loxone.
# Nur sinnvoll, wenn der Heizkreis am Kessel auf „Loxone“ steht (dann entfällt dessen Heizkurve).
HK_SETPOINT_REGS = {"hk1": 6998, "hk2": 6999}
REG_HK2_SETPOINT = HK_SETPOINT_REGS["hk2"]
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
    # Fehlt ein Fühler, meldet der Kessel einen festen Wert (z. B. 120 °C) – ab hier „nicht vorhanden“
    max_valid: float | None = None

    @property
    def limit(self) -> float | None:
        if self.max_valid is not None:
            return self.max_valid
        return 110.0 if self.kind == "temp" else None


READ_REGISTERS: tuple[Reg, ...] = (
    Reg("aussen", 8, max_valid=70),
    Reg("aussen_gemittelt", 6, max_valid=70),
    Reg("kessel_ist", 82),
    Reg("kessel_soll", 84),
    Reg("kesselzustand", 86, "code"),
    Reg("leistung", 88, "percent", precision=0),
    Reg("rauchgas", 126, precision=0, max_valid=400),
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

# ---------- Vorlauf-Berechnung (Heizkurve + Raumbedarf) ----------
CONF_HEAT_LIMIT = "heat_limit"  # ab dieser Außentemperatur nur noch Mindest-Vorlauf
CONF_ROOM_GAIN = "room_gain"  # K Vorlauf je K Raum zu kalt/zu warm
CONF_ROOM_BOOST_MAX = "room_boost_max"
CONF_ROOM_LOWER_MAX = "room_lower_max"
DEFAULT_HEAT_LIMIT = 18.0
DEFAULT_ROOM_GAIN = 3.0
DEFAULT_ROOM_BOOST_MAX = 10.0
DEFAULT_ROOM_LOWER_MAX = 5.0
ROOM_DEADBAND = 0.2  # kleinere Abweichungen ignorieren

# je Heizkreis: f"{hk}_rooms", f"{hk}_out_cold", f"{hk}_flow_cold", f"{hk}_out_warm", f"{hk}_flow_warm"
DEFAULT_CURVE = {"out_cold": -10.0, "flow_cold": 50.0, "out_warm": 15.0, "flow_warm": 28.0}

# Zusatzanforderung je Heizkreis: f"{hk}_request_entities", f"{hk}_request_min"
DEFAULT_REQUEST_MIN = 35
