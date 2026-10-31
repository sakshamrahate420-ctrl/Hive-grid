"""Nagpur weather, PVGIS cache, tariff assumptions, and grid conditions."""
from __future__ import annotations

import bisect
import csv
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
import json
import logging
import math
from pathlib import Path
import random

LOGGER = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent
REAL_DIR = ROOT / "data" / "real"
TARIFF_PATH = ROOT / "tariff" / "msedcl_tariff.json"
# India uses a fixed UTC+05:30 offset (no daylight-saving time); this works on
# Windows without requiring a separately installed IANA tzdata package.
IST = timezone(timedelta(hours=5, minutes=30), "IST")
SOLAR_DERATE = 0.9


class PVGISWeatherProvider:
    """Offline reader/interpolator for a locally cached PVGIS hourly CSV."""

    def __init__(self, year: int, data_dir: Path = REAL_DIR):
        self.year = year
        self.csv_path = data_dir / f"pvgis_nagpur_{year}.csv"
        self.meta_path = data_dir / f"pvgis_nagpur_{year}.meta.json"
        self.rows: list[tuple[datetime, float, float, float]] = []
        self.timestamps: list[datetime] = []
        self.metadata: dict = {}
        if not self.csv_path.is_file():
            raise FileNotFoundError(self.csv_path)
        with self.csv_path.open(newline="", encoding="utf-8") as stream:
            for row in csv.DictReader(stream):
                stamp = datetime.fromisoformat(row["timestamp_ist"])
                self.rows.append((stamp, float(row["temperature_c"]), float(row["irradiance_w_m2"]), float(row["pv_kw_per_kwp"])))
        self.rows.sort(key=lambda item: item[0])
        if len(self.rows) < 24:
            raise ValueError(f"PVGIS cache is incomplete: {self.csv_path}")
        self.timestamps = [row[0] for row in self.rows]
        if self.meta_path.is_file():
            self.metadata = json.loads(self.meta_path.read_text(encoding="utf-8"))

    @property
    def dates(self) -> list[date]:
        return sorted({stamp.date() for stamp, *_ in self.rows if stamp.year == self.year})

    def at(self, local_time: datetime) -> tuple[float, float, float]:
        """Linearly interpolate air temperature, in-plane irradiance, and PV kW/kWp."""
        target = local_time.astimezone(IST)
        index = bisect.bisect_left(self.timestamps, target)
        if index == 0:
            row = self.rows[0]
            return row[1], row[2], row[3]
        if index == len(self.rows):
            row = self.rows[-1]
            return row[1], row[2], row[3]
        left, right = self.rows[index - 1], self.rows[index]
        span = (right[0] - left[0]).total_seconds()
        fraction = (target - left[0]).total_seconds() / span if span else 0.0
        return tuple(left[i] + (right[i] - left[i]) * fraction for i in (1, 2, 3))

    def daily_maxima(self) -> list[tuple[date, float]]:
        maximum: dict[date, float] = {}
        for stamp, temp, *_ in self.rows:
            if stamp.year == self.year:
                maximum[stamp.date()] = max(temp, maximum.get(stamp.date(), -math.inf))
        return sorted(maximum.items(), key=lambda item: (-item[1], item[0]))


@lru_cache(maxsize=8)
def _cached_provider(year: int, data_dir: Path) -> PVGISWeatherProvider:
    """Avoid re-reading the hourly CSV for every sampled date/world instance."""
    return PVGISWeatherProvider(year, data_dir)


def _load_tariff(path: Path = TARIFF_PATH) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        LOGGER.warning("MSEDCL tariff config unavailable at %s: %s; prices and P2P trades disabled", path, exc)
        return {"billing_slabs": [], "tod_slots": [], "feed_in_rupees_per_kwh": None}


@dataclass
class World:
    seed: int
    heatwave: bool = False
    heat_start: int = 72
    heat_end: int = 84
    cap_reduction_pct: float = 20.0
    day_of_year: int = 130
    demo_date: str | None = None
    weather_year: int = 2023
    real_data_dir: Path = field(default=REAL_DIR, repr=False)
    tariff_path: Path = field(default=TARIFF_PATH, repr=False)
    _cloud_cache: dict[int, float] = field(default_factory=dict, init=False, repr=False)
    _provider: PVGISWeatherProvider | None = field(default=None, init=False, repr=False)
    _tariff: dict = field(default_factory=dict, init=False, repr=False)
    _selected_date: date | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self._tariff = _load_tariff(self.tariff_path)
        try:
            self._provider = _cached_provider(self.weather_year, Path(self.real_data_dir))
            selected = date.fromisoformat(self.demo_date) if self.demo_date else None
            available = self._provider.dates
            if selected is None:
                hot_days = [d for d, temp in self._provider.daily_maxima() if temp >= 43.0]
                selected = hot_days[0] if hot_days else (available[0] if available else None)
            if selected is None or selected.year != self.weather_year or selected not in available:
                raise ValueError(f"demo date {selected} is not covered by the {self.weather_year} PVGIS cache")
            self._selected_date = selected
            self.demo_date = selected.isoformat()
            self.day_of_year = selected.timetuple().tm_yday
        except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
            self._provider = None
            self._selected_date = None
            LOGGER.warning("PVGIS weather cache unavailable (%s); using the synthetic weather/solar generator", exc)

    @property
    def weather_is_real(self) -> bool:
        return self._provider is not None

    @property
    def tariff_is_configured(self) -> bool:
        value = self._tariff.get("simulation_energy_charge_rupees_per_kwh")
        if value is None:
            value = self._tariff.get("assumed_defaults", {}).get("simulation_energy_charge_rupees_per_kwh")
        return isinstance(value, (int, float)) and value >= 0

    @property
    def tariff_is_assumed(self) -> bool:
        return self.tariff_is_configured and (self._tariff.get("simulation_energy_charge_rupees_per_kwh") is None
            or self._tariff.get("simulation_energy_charge_status") != "VERIFIED")

    @property
    def tariff_base_price(self) -> float:
        value = self._tariff.get("simulation_energy_charge_rupees_per_kwh")
        if value is None:
            value = self._tariff.get("assumed_defaults", {}).get("simulation_energy_charge_rupees_per_kwh")
        return float(value) if isinstance(value, (int, float)) and value >= 0 else 0.0

    @property
    def p2p_is_configured(self) -> bool:
        feed_in = self._tariff.get("feed_in_rupees_per_kwh")
        if feed_in is None:
            feed_in = self._tariff.get("assumed_defaults", {}).get("feed_in_rupees_per_kwh")
        return self.tariff_is_configured and isinstance(feed_in, (int, float)) and feed_in >= 0

    def tariff_price(self, step: int) -> float:
        """Return configured INR/kWh, or neutral zero when placeholders are unset."""
        if not self.tariff_is_configured:
            return 0.0
        base = self.tariff_base_price
        hour = (step % 96) / 4
        month = self._selected_date.month if self._selected_date else 1
        slot = next((x for x in self._tariff.get("tod_slots", [])
                     if _time_hour(x["start_local"]) <= hour < _time_hour(x["end_local"], end_of_day=True)), None)
        if slot is None:
            return base
        defaults = self._tariff.get("assumed_defaults", {})
        rebate = slot.get("rebate_percent_apr_sep" if 4 <= month <= 9 else "rebate_percent_oct_mar", slot.get("rebate_percent"))
        if rebate is None and slot.get("name") == "solar": rebate = defaults.get("solar_rebate_percent", 0)
        charge = slot.get("charge_percent")
        if charge is None and slot.get("name") == "peak_evening": charge = defaults.get("evening_charge_percent", 0)
        # Rupee-specific adders/rebates are placeholders, so only official percent ToD
        # factors are applied. The configured base rate remains an operator-supplied value.
        return max(0.0, base * (1.0 - float(rebate or 0) / 100.0) * (1.0 + float(charge or 0) / 100.0))

    def p2p_price_band(self, step: int) -> tuple[float, float] | None:
        if not self.p2p_is_configured:
            return None
        feed_in_value = self._tariff.get("feed_in_rupees_per_kwh")
        feed_in = float(feed_in_value if feed_in_value is not None else self._tariff["assumed_defaults"]["feed_in_rupees_per_kwh"])
        grid_price = self.tariff_price(step)
        if feed_in > grid_price:
            LOGGER.warning("Tariff config has feed-in rate above grid price at step %d; P2P trading disabled", step)
            return None
        return feed_in, grid_price

    def is_low_tariff(self, step: int) -> bool:
        """Whether current local time lies in the configured solar-hours window."""
        if not self.tariff_is_configured:
            return False
        hour = (step % 96) / 4
        solar = next((x for x in self._tariff.get("tod_slots", []) if x.get("name") == "solar"), None)
        return bool(solar and _time_hour(solar["start_local"]) <= hour < _time_hour(solar["end_local"], end_of_day=True))

    def weather(self, step: int) -> tuple[float, float, bool]:
        if self._provider is not None and self._selected_date is not None:
            local = datetime.combine(self._selected_date, datetime.min.time(), IST) + timedelta(minutes=(step % 96) * 15)
            temp, irradiance, _ = self._provider.at(local)
            cloud = max(0.0, min(1.0, 1.0 - irradiance / 1000.0))
            return temp, cloud, temp >= 43.0
        rng = random.Random(self.seed * 1000 + step)
        annual = math.cos(2 * math.pi * (self.day_of_year - 130) / 365)
        mean_temperature = 34 + 5 * annual
        hour = (step % 96) / 4
        diurnal = 3.2 * math.cos(2 * math.pi * (hour - 14) / 24)
        temp = mean_temperature + diurnal + (3 if self.heatwave and self.heat_start <= step < self.heat_end else 0) + rng.uniform(-1.2, 1.2)
        cloud = self._cloud_cache.get(step)
        if cloud is None:
            start = max(self._cloud_cache, default=-1) + 1
            cloud = self._cloud_cache.get(start - 1, .55)
            for index in range(start, step + 1):
                cloud_rng = random.Random(self.seed * 1000 + index + 71)
                cloud = max(.05, min(1, .55 + .78 * (cloud - .55) + cloud_rng.uniform(-.12, .12)))
                self._cloud_cache[index] = cloud
        return temp, cloud, temp >= 43

    def solar_kw(self, kwp: float, step: int, cloud: float, day_of_year: int | None = None) -> float:
        if self._provider is not None and self._selected_date is not None:
            local = datetime.combine(self._selected_date, datetime.min.time(), IST) + timedelta(minutes=(step % 96) * 15)
            _, _, per_kwp = self._provider.at(local)
            return max(0.0, per_kwp * max(0.0, kwp) * SOLAR_DERATE)
        hour = (step % 96) / 4
        day = self.day_of_year if day_of_year is None else day_of_year
        latitude = math.radians(21.15)
        declination = math.radians(23.45) * math.sin(2 * math.pi * (284 + day) / 365)
        hour_angle = math.radians(15 * (hour - 12))
        daylight = max(0.0, math.sin(latitude) * math.sin(declination) + math.cos(latitude) * math.cos(declination) * math.cos(hour_angle))
        return kwp * daylight * (1 - .65 * cloud)

    def price(self, step: int) -> float:
        return self.tariff_price(step)

    def price_feature(self, step: int) -> float:
        """Return a unitless feature based on the configured or labeled assumed tariff."""
        if not self.tariff_is_configured:
            return 0.0
        base=self.tariff_base_price
        return max(0.0,min(1.0,self.price(step)/max(base*1.2,1e-9)))

    def is_stress(self, step: int, net_load_kw: float = 0.0, n_homes: int = 1) -> bool:
        """Detect a manual heatwave event, a hot evening, or cap exceedance."""
        hour = (step % 96) / 4
        temp, _, _ = self.weather(step)
        base_cap = n_homes * 2.7
        return bool((self.heatwave and self.heat_start <= step < self.heat_end) or (temp >= 43 and 18 <= hour < 22) or net_load_kw > base_cap)

    def cap_kw(self, n: int, step: int) -> float:
        cap = n * 2.7
        temp, _, _ = self.weather(step)
        hour = (step % 96) / 4
        event = (self.heatwave and self.heat_start <= step < self.heat_end) or (temp >= 43 and 18 <= hour < 22)
        return cap * (1 - self.cap_reduction_pct / 100) if event else cap

    def provenance(self) -> dict:
        meta = self._provider.metadata if self._provider else {}
        return {
            "location": {"name": "Nagpur", "latitude": 21.15, "longitude": 79.09},
            "demo_date": self.demo_date,
            "weather": {"status": "real_cached" if self.weather_is_real else "synthetic_fallback", "source": meta.get("source", "Synthetic seasonal generator"), "database": meta.get("radiation_database"), "cache": str(self._provider.csv_path) if self._provider else None, "year": self.weather_year, "variables": ["historical 2 m air temperature", "historical in-plane irradiance"] if self.weather_is_real else ["synthetic air temperature", "synthetic cloud proxy"]},
            "solar": {"status": "modeled_from_real_pvgis" if self.weather_is_real else "synthetic_model", "source": "PVGIS 1 kWp output x home kWp x 0.9 derate" if self.weather_is_real else "synthetic geometry/cloud model", "derate": SOLAR_DERATE if self.weather_is_real else None},
            "tariff": {"status": "ASSUMED" if self.tariff_is_assumed else ("configured" if self.tariff_is_configured else "assumption_placeholders_unset"), "config": str(self.tariff_path), "currency_rates_are_assumptions": True, "rupee_rates_configured": self.tariff_is_configured, "p2p_trading_enabled": self.p2p_is_configured},
            "household_loads": {"status": "synthetic", "source": "seeded household profile generator; no real household meter data"},
            "runtime_internet_required": False,
        }


def _time_hour(value: str, end_of_day: bool = False) -> float:
    if end_of_day and value == "24:00":
        return 24.0
    hour, minute = (int(part) for part in value.split(":"))
    return hour + minute / 60.0
