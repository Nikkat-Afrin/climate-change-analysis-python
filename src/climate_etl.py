"""ETL pipeline: raw IMF Climate-Data-Portal exports -> tidy annual dataset.

The three raw exports each use a different layout:

    atmospheric_co2.csv      monthly rows, dates like "1958M03"
    mean_sea_levels.csv      per-sea satellite passes, dates like "D12/17/1992"
    surface_temperature.csv  wide format, one column per year (1961..2023)

This module extracts them, runs explicit data-quality validation, reshapes
everything to one row per year, and loads a merged analysis-ready table:

    data/processed/climate_annual.csv
        year, co2_ppm, temp_anomaly_c, sea_level_mm

Run:  python src/climate_etl.py            (from the repo root)
      python src/climate_etl.py --strict   (fail on any DQ warning)
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path

import pandas as pd

log = logging.getLogger("climate_etl")

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data"
PROCESSED = RAW / "processed"

# Plausibility ranges for data-quality checks
VALUE_RANGES = {
    "co2_ppm": (250.0, 450.0),          # Mauna Loa era
    "temp_anomaly_c": (-3.0, 3.0),      # global annual anomaly vs 1951-80
    "sea_level_mm": (-150.0, 300.0),    # satellite-era change vs reference
}


class DataQualityError(Exception):
    """Raised in --strict mode when a data-quality check fails."""


# ------------------------------------------------------------------ extract --

def extract(name: str, path: Path | None = None) -> pd.DataFrame:
    """Read one raw export; validates the file exists and is non-empty."""
    path = path or RAW / f"{name}.csv"
    if not path.exists():
        raise FileNotFoundError(f"raw input missing: {path}")
    df = pd.read_csv(path, encoding="utf-8-sig")  # strip BOM from portal exports
    if df.empty:
        raise DataQualityError(f"{path.name}: file is empty")
    log.info("extracted %s: %d rows x %d cols", path.name, *df.shape)
    return df


# ----------------------------------------------------------------- validate --

def require_columns(df: pd.DataFrame, columns: list[str], source: str) -> None:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise DataQualityError(f"{source}: missing required columns {missing}")


def check_range(series: pd.Series, metric: str, strict: bool) -> list[str]:
    lo, hi = VALUE_RANGES[metric]
    bad = series[(series < lo) | (series > hi)].dropna()
    issues = []
    if len(bad):
        msg = f"{metric}: {len(bad)} values outside plausible range [{lo}, {hi}]"
        issues.append(msg)
        if strict:
            raise DataQualityError(msg)
        log.warning("%s (kept, flagged)", msg)
    return issues


def check_year_continuity(years: pd.Series, metric: str, strict: bool) -> list[str]:
    years = years.sort_values()
    gaps = sorted(set(range(int(years.min()), int(years.max()) + 1)) - set(years))
    issues = []
    if gaps:
        msg = f"{metric}: missing years {gaps[:10]}{'...' if len(gaps) > 10 else ''}"
        issues.append(msg)
        if strict:
            raise DataQualityError(msg)
        log.warning(msg)
    return issues


# ---------------------------------------------------------------- transform --

def transform_co2(df: pd.DataFrame) -> pd.DataFrame:
    """Monthly 'YYYYMmm' rows -> annual mean ppm.

    The raw export interleaves two indicators (ppm concentrations and
    year-on-year percentage change); only Parts-Per-Million rows are ppm.
    """
    require_columns(df, ["Date", "Value", "Unit"], "atmospheric_co2")
    ppm = df[df["Unit"].astype(str).str.strip().eq("Parts Per Million")]
    if ppm.empty:
        raise DataQualityError("atmospheric_co2: no 'Parts Per Million' rows")
    monthly = ppm[ppm["Date"].astype(str).str.match(r"^\d{4}M\d{2}$")].copy()
    monthly["year"] = monthly["Date"].str.slice(0, 4).astype(int)
    monthly["Value"] = pd.to_numeric(monthly["Value"], errors="coerce")
    # Quarantine physically implausible monthly readings before aggregation
    # (the 2023 portal export ends with a corrupt "2024M01,0.68" row).
    lo, hi = VALUE_RANGES["co2_ppm"]
    bad = monthly[(monthly["Value"] < lo) | (monthly["Value"] > hi)]
    if len(bad):
        log.warning("atmospheric_co2: quarantined %d implausible monthly rows: %s",
                    len(bad), bad[["Date", "Value"]].to_dict("records"))
        monthly = monthly.drop(bad.index)
    annual = (monthly.dropna(subset=["Value"])
              .groupby("year", as_index=False)["Value"].mean()
              .rename(columns={"Value": "co2_ppm"}))
    annual["co2_ppm"] = annual["co2_ppm"].round(2)
    return annual


def transform_sea_level(df: pd.DataFrame) -> pd.DataFrame:
    """Per-sea satellite passes ('D12/17/1992') -> annual global mean (mm)."""
    require_columns(df, ["Date", "Value", "Measure"], "mean_sea_levels")
    out = df.copy()
    out["date"] = pd.to_datetime(out["Date"].astype(str).str.lstrip("D"),
                                 format="%m/%d/%Y", errors="coerce")
    out["Value"] = pd.to_numeric(out["Value"], errors="coerce")
    out = out.dropna(subset=["date", "Value"])
    out["year"] = out["date"].dt.year
    # Mean per sea per year first, then across seas, so seas with more
    # satellite passes don't dominate the global average.
    per_sea = out.groupby(["Measure", "year"], as_index=False)["Value"].mean()
    annual = (per_sea.groupby("year", as_index=False)["Value"].mean()
              .rename(columns={"Value": "sea_level_mm"}))
    annual["sea_level_mm"] = annual["sea_level_mm"].round(2)
    return annual


def transform_temperature(df: pd.DataFrame) -> pd.DataFrame:
    """Wide per-country year columns -> annual World anomaly (deg C)."""
    require_columns(df, ["Country"], "surface_temperature")
    year_cols = [c for c in df.columns if re.fullmatch(r"(19|20)\d{2}", str(c))]
    if not year_cols:
        raise DataQualityError("surface_temperature: no year columns found")

    world = df[df["Country"].astype(str).str.strip().eq("World")]
    if len(world):
        series = world.iloc[0][year_cols]
        log.info("temperature: using the 'World' aggregate row")
    else:  # fall back to unweighted country mean
        series = df[year_cols].apply(pd.to_numeric, errors="coerce").mean()
        log.warning("temperature: no 'World' row; using unweighted country mean")

    annual = (series.rename("temp_anomaly_c").rename_axis("year").reset_index())
    annual["year"] = annual["year"].astype(int)
    annual["temp_anomaly_c"] = pd.to_numeric(annual["temp_anomaly_c"],
                                             errors="coerce").round(3)
    return annual.dropna(subset=["temp_anomaly_c"])


def merge_annual(co2: pd.DataFrame, temp: pd.DataFrame,
                 sea: pd.DataFrame) -> pd.DataFrame:
    merged = co2.merge(temp, on="year", how="outer").merge(sea, on="year", how="outer")
    return merged.sort_values("year").reset_index(drop=True)


# --------------------------------------------------------------------- load --

def load(df: pd.DataFrame, path: Path | None = None) -> Path:
    path = path or PROCESSED / "climate_annual.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    log.info("loaded %d rows -> %s", len(df), path)
    return path


# --------------------------------------------------------------------- run ---

def run(strict: bool = False) -> dict:
    """Execute the full pipeline; returns a data-quality report."""
    co2 = transform_co2(extract("atmospheric_co2"))
    temp = transform_temperature(extract("surface_temperature"))
    sea = transform_sea_level(extract("mean_sea_levels"))

    issues: list[str] = []
    issues += check_range(co2["co2_ppm"], "co2_ppm", strict)
    issues += check_range(temp["temp_anomaly_c"], "temp_anomaly_c", strict)
    issues += check_range(sea["sea_level_mm"], "sea_level_mm", strict)
    issues += check_year_continuity(co2["year"], "co2_ppm", strict)
    issues += check_year_continuity(temp["year"], "temp_anomaly_c", strict)

    merged = merge_annual(co2, temp, sea)
    out_path = load(merged)

    report = {
        "rows": int(len(merged)),
        "year_range": [int(merged["year"].min()), int(merged["year"].max())],
        "complete_rows": int(merged.dropna().shape[0]),
        "dq_issues": issues,
        "output": str(out_path.relative_to(ROOT)),
    }
    log.info("DQ report: %s", json.dumps(report, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true",
                        help="fail on any data-quality warning")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run(strict=args.strict)


if __name__ == "__main__":
    main()
