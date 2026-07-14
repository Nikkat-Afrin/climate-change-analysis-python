"""Tests for the climate ETL pipeline — real raw files + synthetic edge cases."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from climate_etl import (DataQualityError, check_range, check_year_continuity,  # noqa: E402
                         extract, merge_annual, run, transform_co2,
                         transform_sea_level, transform_temperature)


# ------------------------------------------------------------ real inputs ---

def test_extract_strips_bom():
    df = extract("atmospheric_co2")
    assert "ObjectId" in df.columns  # would be "﻿ObjectId" without BOM handling


def test_co2_annual_values_are_physical():
    annual = transform_co2(extract("atmospheric_co2"))
    assert annual["year"].min() == 1958
    first = annual.loc[annual["year"] == 1958, "co2_ppm"].iloc[0]
    assert 310 < first < 320          # Mauna Loa 1958 ~315 ppm
    recent = annual.loc[annual["year"] == 2023, "co2_ppm"].iloc[0]
    assert 415 < recent < 430
    # the corrupt 2024M01 row must have been quarantined
    assert annual["co2_ppm"].between(250, 450).all()


def test_temperature_uses_world_row():
    annual = transform_temperature(extract("surface_temperature"))
    assert annual["year"].min() == 1961
    assert annual["temp_anomaly_c"].between(-3, 3).all()
    recent = annual.loc[annual["year"] >= 2015, "temp_anomaly_c"]
    early = annual.loc[annual["year"] <= 1970, "temp_anomaly_c"]
    assert recent.mean() > early.mean() + 0.5   # warming signal present


def test_sea_level_annualized_per_sea_first():
    annual = transform_sea_level(extract("mean_sea_levels"))
    assert annual["year"].min() >= 1992          # satellite era
    assert annual["sea_level_mm"].is_monotonic_increasing or \
        annual["sea_level_mm"].iloc[-1] > annual["sea_level_mm"].iloc[0]


def test_run_end_to_end(tmp_path):
    report = run(strict=False)
    assert report["rows"] >= 60
    assert report["year_range"][0] == 1958
    assert report["complete_rows"] >= 25
    out = Path(__file__).resolve().parents[1] / report["output"]
    produced = pd.read_csv(out)
    assert list(produced.columns) == ["year", "co2_ppm", "temp_anomaly_c", "sea_level_mm"]


# ------------------------------------------------------- synthetic checks ---

def test_missing_column_raises():
    with pytest.raises(DataQualityError, match="missing required columns"):
        transform_co2(pd.DataFrame({"Date": ["1990M01"]}))


def test_range_check_strict_raises():
    s = pd.Series([300.0, 9999.0])
    with pytest.raises(DataQualityError):
        check_range(s, "co2_ppm", strict=True)
    issues = check_range(s, "co2_ppm", strict=False)
    assert len(issues) == 1


def test_year_continuity_detects_gaps():
    years = pd.Series([1990, 1991, 1994])
    issues = check_year_continuity(years, "co2_ppm", strict=False)
    assert issues and "1992" in issues[0]


def test_merge_is_outer_and_sorted():
    co2 = pd.DataFrame({"year": [2000, 2001], "co2_ppm": [370.0, 371.0]})
    temp = pd.DataFrame({"year": [2001, 2002], "temp_anomaly_c": [0.5, 0.6]})
    sea = pd.DataFrame({"year": [1999], "sea_level_mm": [5.0]})
    merged = merge_annual(co2, temp, sea)
    assert list(merged["year"]) == [1999, 2000, 2001, 2002]
    assert merged["co2_ppm"].isna().sum() == 2


def test_empty_ppm_rows_raise():
    df = pd.DataFrame({"Date": ["1990M01"], "Value": [1.0], "Unit": ["Percent"]})
    with pytest.raises(DataQualityError, match="Parts Per Million"):
        transform_co2(df)
