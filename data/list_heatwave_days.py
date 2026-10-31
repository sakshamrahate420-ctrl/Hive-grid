"""List cached Nagpur dates with hourly PVGIS Tmax >= 43 C, hottest first."""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from world import PVGISWeatherProvider  # noqa: E402


def hottest_days(year: int, data_dir: Path, threshold_c: float = 43.0) -> list[tuple[date, float]]:
    provider = PVGISWeatherProvider(year, data_dir)
    return [(day, maximum) for day, maximum in provider.daily_maxima() if maximum >= threshold_c]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2023)
    parser.add_argument("--threshold-c", type=float, default=43.0)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parent / "real")
    args = parser.parse_args()
    days = hottest_days(args.year, args.data_dir, args.threshold_c)
    if not days:
        print(f"No cached days reached {args.threshold_c:g} C in {args.year}.")
        return
    print("date        Tmax_C")
    for day, maximum in days[:args.limit]:
        print(f"{day.isoformat()}  {maximum:.2f}")


if __name__ == "__main__":
    main()
