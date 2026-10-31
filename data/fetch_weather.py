"""Fetch and cache hourly PVGIS weather/solar data for Nagpur.

The application reads the cache only. Network access is used only when this
script is explicitly run by a developer.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

LATITUDE = 21.15
LONGITUDE = 79.09
ENDPOINT = "https://re.jrc.ec.europa.eu/api/v5_3/seriescalc"
IST = timezone(timedelta(hours=5, minutes=30), "IST")
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "real"


def fetch_year(year: int, output_dir: Path = DEFAULT_OUTPUT, timeout: int = 90) -> tuple[Path, Path]:
    """Download hourly PVGIS data, convert stamps to IST, and persist CSV + metadata."""
    if not 2005 <= year <= datetime.now(timezone.utc).year:
        raise ValueError("year must be between 2005 and the current UTC year")
    params = {
        "lat": LATITUDE,
        "lon": LONGITUDE,
        "startyear": year,
        "endyear": year,
        "pvcalculation": 1,
        "peakpower": 1,
        "loss": 0,
        "outputformat": "json",
        "components": 1,
        "usehorizon": 1,
    }
    url = f"{ENDPOINT}?{urlencode(params)}"
    request = Request(url)
    with urlopen(request, timeout=timeout) as response:
        payload = json.load(response)

    hourly = payload.get("outputs", {}).get("hourly", [])
    if not hourly:
        raise RuntimeError("PVGIS returned no hourly observations")
    start = datetime(year, 1, 1, tzinfo=IST)
    end = datetime(year + 1, 1, 2, tzinfo=IST)
    records = []
    for row in hourly:
        utc = datetime.strptime(row["time"], "%Y%m%d:%H%M").replace(tzinfo=timezone.utc)
        local = utc.astimezone(IST)
        if not start <= local < end:
            continue
        irradiance = row.get("G(i)")
        if irradiance is None:
            irradiance = sum(float(row.get(key, 0) or 0) for key in ("Gb(i)", "Gd(i)", "Gr(i)"))
        records.append({
            "timestamp_utc": utc.isoformat(),
            "timestamp_ist": local.isoformat(),
            "temperature_c": float(row["T2m"]),
            "irradiance_w_m2": float(irradiance),
            "pv_kw_per_kwp": float(row.get("P", 0) or 0) / 1000.0,
        })
    if not records:
        raise RuntimeError("PVGIS returned hourly data, but none covered the requested local year")

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"pvgis_nagpur_{year}.csv"
    metadata_path = output_dir / f"pvgis_nagpur_{year}.meta.json"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    meta = {
        "source": "European Commission Joint Research Centre PVGIS 5.3 seriescalc API",
        "source_url": url,
        "requested_year": year,
        "source_utc_years": [year],
        "location": {"name": "Nagpur", "latitude": LATITUDE, "longitude": LONGITUDE},
        "radiation_database": payload.get("inputs", {}).get("meteo_data", {}).get("radiation_db"),
        "meteo_database": payload.get("inputs", {}).get("meteo_data", {}).get("meteo_db"),
        "observation_count": len(records),
        "timestamp_note": "PVGIS hourly UTC timestamps converted to Asia/Kolkata (IST); the local-year ending boundary records are retained when available in the requested UTC year.",
        "units": {"temperature_c": "degC", "irradiance_w_m2": "W/m2", "pv_kw_per_kwp": "kW per kWp"},
        "pv_model": {"peakpower_kwp": 1, "system_loss_percent": 0, "technology": "PVGIS default crystalline silicon", "runtime_derate": 0.9},
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "pvgis_metadata": payload.get("meta", {}),
    }
    metadata_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return csv_path, metadata_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2023, help="PVGIS historical year to cache (default: 2023)")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()
    csv_path, metadata_path = fetch_year(args.year, args.output_dir, args.timeout)
    print(f"Cached PVGIS weather: {csv_path}")
    print(f"Metadata: {metadata_path}")


if __name__ == "__main__":
    main()
