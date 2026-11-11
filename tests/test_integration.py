"""Tests gegen den nachgebauten Kessel."""

from __future__ import annotations

from datetime import timedelta

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed, mock_restore_cache

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, State
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util

from custom_components.hargassner_modbus.const import DOMAIN
from custom_components.hargassner_modbus.modbus import ModbusClient, ModbusError, decode_float

from .fake_boiler import BOILER_VALUES, FakeBoiler



@pytest.fixture
async def boiler():
    b = FakeBoiler(BOILER_VALUES, word_swap=True)
    port = await b.start()
    b.port = port
    yield b
    await b.stop()


async def test_client_read_write(boiler):
    c = ModbusClient("127.0.0.1", boiler.port, 1)
    assert decode_float(await c.read_holding(8, 2), True) == pytest.approx(4.5)
    await c.write_registers(6999, [45])
    assert boiler.writes == [(6999, [45])]
    with pytest.raises(ModbusError):
        await c.read_holding(5000, 2)  # nicht vorhanden -> Modbus-Fehler
    await c.close()


async def test_client_no_server():
    c = ModbusClient("127.0.0.1", 1, 1, timeout=1)
    with pytest.raises(ModbusError):
        await c.read_holding(6499, 2)


async def _setup_via_flow(hass: HomeAssistant, port: int):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "127.0.0.1", "port": port, "unit": 1, "boiler_type": "nano"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY, result
    await hass.async_block_till_done(wait_background_tasks=True)
    return result


@pytest.mark.parametrize("swap", [True, False])
async def test_flow_detects_word_order_and_entities(hass: HomeAssistant, swap):
    b = FakeBoiler(BOILER_VALUES, word_swap=swap)
    port = await b.start()
    try:
        result = await _setup_via_flow(hass, port)
        assert result["options"]["word_swap"] is swap
        assert hass.states.get("sensor.hargassner_outdoor_temperature").state == "4.5"
        assert hass.states.get("sensor.hargassner_boiler_temperature").state == "71.5"
        assert hass.states.get("sensor.hargassner_boiler_state").state == "Leistungsbrand"
        assert hass.states.get("sensor.hargassner_state_hc2").state == "Restwärme"
        assert hass.states.get("binary_sensor.hargassner_residual_heat_hc2").state == "on"
        assert hass.states.get("binary_sensor.hargassner_fault").state == "off"
        assert hass.states.get("sensor.hargassner_pellet_stock").state == "2350"
        # Schalter nach Einrichtung aus, nichts geschrieben
        assert hass.states.get("switch.hargassner_control_hc2").state == "off"
        assert b.writes == []
    finally:
        await b.stop()


async def test_flow_cannot_connect(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "127.0.0.1", "port": 1, "unit": 1, "boiler_type": "nano"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_keepalive_and_hk2_write(hass: HomeAssistant, boiler):
    await _setup_via_flow(hass, boiler.port)
    # Lebenszeichen alle 10 s
    n = boiler.reads.count(6499)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=15))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert boiler.reads.count(6499) == n + 1

    # Vorgabe setzen: ohne Freigabe kein Schreiben
    await hass.services.async_call("number", "set_value", {"entity_id": "number.hargassner_flow_hc2_setpoint", "value": 44.6}, blocking=True)
    assert boiler.writes == []
    # Freigabe -> sofort schreiben (gerundet)
    await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.hargassner_control_hc2"}, blocking=True)
    assert boiler.writes[-1] == (6999, [45])
    # Grenze: über Höchstwert wird begrenzt
    await hass.services.async_call("number", "set_value", {"entity_id": "number.hargassner_flow_hc2_setpoint", "value": 60}, blocking=True)
    assert boiler.writes[-1] == (6999, [60])
    # zyklisch alle 60 s
    k = len(boiler.writes)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(boiler.writes) == k + 1
    # Aus -> kein Schreiben mehr
    await hass.services.async_call("switch", "turn_off", {"entity_id": "switch.hargassner_control_hc2"}, blocking=True)
    k = len(boiler.writes)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=130))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(boiler.writes) == k


async def test_restore_after_restart(hass: HomeAssistant, boiler):
    mock_restore_cache(hass, [State("switch.hargassner_control_hc2", "on"), State("number.hargassner_flow_hc2_setpoint", "41")])
    entry = MockConfigEntry(
        domain=DOMAIN, data={"host": "127.0.0.1", "port": boiler.port, "unit": 1},
        options={"word_swap": True, "boiler_type": "nano", "hk2_min": 20, "hk2_max": 60, "extras": False},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get("switch.hargassner_control_hc2").state == "on"
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert boiler.writes and boiler.writes[-1] == (6999, [41])


async def test_unavailable_when_boiler_gone(hass: HomeAssistant, boiler):
    await _setup_via_flow(hass, boiler.port)
    await boiler.stop()
    # offene Verbindung schließen lassen
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    await entry.runtime_data.client.close()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=15))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get("sensor.hargassner_outdoor_temperature").state == "unavailable"


async def test_german_names(hass: HomeAssistant, boiler):
    hass.config.language = "de"
    await _setup_via_flow(hass, boiler.port)
    ids = sorted(s.entity_id for s in hass.states.async_all() if s.entity_id.split(".")[1].startswith("hargassner"))
    assert "sensor.hargassner_aussentemperatur" in ids
    assert "sensor.hargassner_zustand_hk2" in ids
    assert "switch.hargassner_hk2_vorgeben" in ids
    assert "number.hargassner_vorlauf_hk2_vorgabe" in ids
    assert "switch.hargassner_hk1_vorgeben" in ids
    assert "number.hargassner_vorlauf_hk1_vorgabe" in ids
    assert "binary_sensor.hargassner_storung" in ids
    print("\nIDS", ids)


async def test_options_extras_and_limits(hass: HomeAssistant):
    values = {**BOILER_VALUES, 122: 65.0, 124: 40.0, 254: 55.0, 10: 52.0, 190: 1.0}
    b = FakeBoiler(values)
    port = await b.start()
    try:
        await _setup_via_flow(hass, port)
        entry = hass.config_entries.async_entries(DOMAIN)[0]
        # Allgemein: Puffer/Boiler an
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] is FlowResultType.MENU
        result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "general"})
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {"boiler_type": "nano", "extras": True, "word_swap": True, "heat_limit": 18, "room_gain": 3, "room_boost_max": 10, "room_lower_max": 5},
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done(wait_background_tasks=True)
        # Heizkreis 2: Grenzen
        hk2 = {"min": 50, "max": 40, "rooms": [], "out_cold": -10, "flow_cold": 50, "out_warm": 15, "flow_warm": 28}
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "hk2"})
        result = await hass.config_entries.options.async_configure(result["flow_id"], hk2)
        assert result["errors"] == {"base": "min_max"}
        result = await hass.config_entries.options.async_configure(result["flow_id"], {**hk2, "min": 25, "max": 50})
        assert result["type"] is FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done(wait_background_tasks=True)
        assert hass.states.get("sensor.hargassner_buffer_top").state == "65.0"
        st = hass.states.get("number.hargassner_flow_hc2_setpoint")
        assert st.attributes["max"] == 50
        await hass.services.async_call("number", "set_value", {"entity_id": "number.hargassner_flow_hc2_setpoint", "value": 48}, blocking=True)
        await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.hargassner_control_hc2"}, blocking=True)
        assert b.writes[-1] == (6999, [48])
    finally:
        await b.stop()


async def test_hk1_write_independent(hass: HomeAssistant, boiler):
    await _setup_via_flow(hass, boiler.port)
    # beide Schalter sind nach der Einrichtung aus
    assert hass.states.get("switch.hargassner_control_hc1").state == "off"
    assert hass.states.get("switch.hargassner_control_hc2").state == "off"
    await hass.services.async_call("number", "set_value", {"entity_id": "number.hargassner_flow_hc1_setpoint", "value": 38}, blocking=True)
    await hass.services.async_call("number", "set_value", {"entity_id": "number.hargassner_flow_hc2_setpoint", "value": 33}, blocking=True)
    assert boiler.writes == []
    # nur HK1 frei -> nur 6998
    await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.hargassner_control_hc1"}, blocking=True)
    assert boiler.writes == [(6998, [38])]
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert {w[0] for w in boiler.writes} == {6998}
    # HK2 dazu -> beide im Takt
    await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.hargassner_control_hc2"}, blocking=True)
    assert boiler.writes[-1] == (6999, [33])
    k = len(boiler.writes)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=125))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert sorted(boiler.writes[k:]) == [(6998, [38]), (6999, [33])]



async def test_flow_calculation_and_auto(hass: HomeAssistant, boiler):
    await _setup_via_flow(hass, boiler.port)
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    # zwei Räume an HK2, einer zu kalt
    hass.states.async_set("climate.eg_bad", "heat", {"current_temperature": 21.0, "temperature": 22.0, "friendly_name": "EG Bad"})
    hass.states.async_set("climate.eg_wohnen", "heat", {"current_temperature": 21.5, "temperature": 21.0, "friendly_name": "EG Wohnen"})
    hass.states.async_set("climate.eg_gast", "off", {"current_temperature": 15.0, "temperature": 21.0})
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "hk2"})
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"min": 20, "max": 60, "rooms": ["climate.eg_bad", "climate.eg_wohnen", "climate.eg_gast"],
         "out_cold": -10, "flow_cold": 50, "out_warm": 15, "flow_warm": 28},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done(wait_background_tasks=True)
    # gemittelt 6 °C -> Kurve 35,9 °C; Bad 1 K zu kalt -> +3 K -> 39 °C; Gast ist aus und zählt nicht
    st = hass.states.get("sensor.hargassner_flow_hc2_calculated")
    assert st.state == "39"
    assert st.attributes["kurve"] == 35.9
    assert st.attributes["raum"] == "EG Bad"
    assert st.attributes["raeume"] == 2
    # HK1 ohne Räume: nur Kurve
    assert hass.states.get("sensor.hargassner_flow_hc1_calculated").state == "36"

    # Automatik an, Vorgeben noch aus -> nichts schreiben
    await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.hargassner_automatic_hc2"}, blocking=True)
    assert boiler.writes == []
    await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.hargassner_control_hc2"}, blocking=True)
    assert boiler.writes[-1] == (6999, [39])
    # alle Räume warm -> Absenkung, höchstens 5 K
    hass.states.async_set("climate.eg_bad", "heat", {"current_temperature": 24.0, "temperature": 22.0, "friendly_name": "EG Bad"})
    hass.states.async_set("climate.eg_wohnen", "heat", {"current_temperature": 23.0, "temperature": 21.0, "friendly_name": "EG Wohnen"})
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert boiler.writes[-1] == (6999, [31])
    # Automatik aus -> wieder die manuelle Vorgabe
    await hass.services.async_call("number", "set_value", {"entity_id": "number.hargassner_flow_hc2_setpoint", "value": 44}, blocking=True)
    await hass.services.async_call("switch", "turn_off", {"entity_id": "switch.hargassner_automatic_hc2"}, blocking=True)
    assert boiler.writes[-1] == (6999, [44])
    # Raum nachträglich entfernen
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "hk2"})
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"min": 20, "max": 60, "rooms": ["climate.eg_wohnen"], "out_cold": -10, "flow_cold": 50, "out_warm": 15, "flow_warm": 28},
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    st = hass.states.get("sensor.hargassner_flow_hc2_calculated")
    assert st.attributes["raeume"] == 1
    assert st.attributes["raum"] == "EG Wohnen"
