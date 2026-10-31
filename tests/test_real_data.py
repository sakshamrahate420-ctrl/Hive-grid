import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app
from agents.grid import GridAgent
from collect import _date_partitions
from market import clear_market
from world import PVGISWeatherProvider, World

IST = timezone(timedelta(hours=5, minutes=30), "IST")


def _cache(directory: Path, year: int = 2023, count: int = 96) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"pvgis_nagpur_{year}.csv"
    start = datetime(year, 1, 1, tzinfo=IST)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["timestamp_utc", "timestamp_ist", "temperature_c", "irradiance_w_m2", "pv_kw_per_kwp"])
        writer.writeheader()
        for i in range(count):
            stamp = start + timedelta(hours=i)
            writer.writerow({"timestamp_utc": stamp.astimezone(timezone.utc).isoformat(), "timestamp_ist": stamp.isoformat(), "temperature_c": 20 + i / 100, "irradiance_w_m2": 500, "pv_kw_per_kwp": .8})
    (directory / f"pvgis_nagpur_{year}.meta.json").write_text(json.dumps({"source": "PVGIS test fixture", "radiation_database": "test"}), encoding="utf-8")


def test_pvgis_provider_interpolates_and_derates(tmp_path):
    _cache(tmp_path)
    world = World(4, demo_date="2023-01-01", real_data_dir=tmp_path)
    temperature, cloud, hot = world.weather(1)
    assert world.weather_is_real
    assert temperature == 20.0025
    assert 0 <= cloud <= 1 and not hot
    assert abs(world.solar_kw(2, 1, cloud) - 1.44) < 1e-9
    assert world.provenance()["weather"]["status"] == "real_cached"


def test_missing_cache_falls_back_to_deterministic_synthetic(caplog, tmp_path):
    first = World(9, real_data_dir=tmp_path)
    second = World(9, real_data_dir=tmp_path)
    assert not first.weather_is_real
    assert first.weather(20) == second.weather(20)
    assert "using the synthetic weather/solar generator" in caplog.text
    assert first.provenance()["household_loads"]["status"] == "synthetic"


def test_tariff_placeholders_disable_prices_and_p2p(tmp_path):
    tariff = {"billing_slabs": [], "tod_slots": [], "feed_in_rupees_per_kwh": None, "simulation_energy_charge_rupees_per_kwh": None}
    path = tmp_path / "tariff.json"
    path.write_text(json.dumps(tariff), encoding="utf-8")
    world = World(1, real_data_dir=tmp_path, tariff_path=path)
    assert world.price(40) == 0
    assert world.p2p_price_band(40) is None
    assert not world.is_low_tariff(40)


def test_repository_tariff_uses_labeled_assumptions_and_enables_p2p():
    world = World(2)
    band = world.p2p_price_band(40)
    assert world.provenance()["tariff"]["status"] == "ASSUMED"
    assert world.provenance()["tariff"]["p2p_trading_enabled"] is True
    assert band is not None and band == (2.0, 8.5)
    assert world.price_feature(40) > 0


def test_grid_agent_uses_resolved_assumed_tariff():
    world = World(2)
    agent = GridAgent(world)
    agent.observe(step=0, net_load=100, n_homes=56)
    signal = agent.act(learned_action=[0.5, 0.5, 1.0])
    assert 0 <= signal["price"] <= world.price(0)


def test_configured_tariff_price_and_p2p_stay_in_band(tmp_path):
    _cache(tmp_path)
    tariff = {
        "billing_slabs": [],
        "simulation_energy_charge_rupees_per_kwh": 10,
        "feed_in_rupees_per_kwh": 2,
        "tod_slots": [
            {"name": "solar", "start_local": "09:00", "end_local": "17:00", "rebate_percent_apr_sep": 15, "rebate_percent_oct_mar": 25},
            {"name": "peak_evening", "start_local": "17:00", "end_local": "24:00", "charge_percent": 20},
        ],
    }
    path = tmp_path / "tariff.json"
    path.write_text(json.dumps(tariff), encoding="utf-8")
    world = World(1, demo_date="2023-01-01", real_data_dir=tmp_path, tariff_path=path)
    band = world.p2p_price_band(40)
    assert band == (2, 7.5)
    trades, _ = clear_market([{"home": "H1", "kwh": 1, "price": band[0]}], [{"home": "H2", "kwh": 1, "price": band[1]}], *band)
    assert band[0] <= trades[0]["price"] <= band[1]


def test_date_splits_reserve_demo_date_for_test(tmp_path):
    year = 2023
    _cache(tmp_path, year, count=24 * 40)
    demo = datetime(year, 1, 20).date()
    splits = _date_partitions(year, demo, tmp_path)
    assert demo in splits["test"]
    assert demo not in splits["train"] and demo not in splits["validation"]
    assert not (set(splits["train"]) & set(splits["validation"]))
    assert not (set(splits["train"]) & set(splits["test"]))
    assert not (set(splits["validation"]) & set(splits["test"]))


def test_data_provenance_endpoint():
    response = TestClient(app).get("/data/provenance")
    assert response.status_code == 200
    data = response.json()
    assert data["household_loads"]["status"] == "synthetic"
    assert data["runtime_internet_required"] is False
