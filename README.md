# Climate Change: CO₂, Temperature, Sea Level & Disasters 🌍🌡️

**A multi-dataset study of how atmospheric CO₂, global surface temperature, mean sea level, and climate-related disaster frequency move together over time - and what their interplay implies for disaster risk.**

[![CI](https://github.com/Nikkat-Afrin/climate-change-analysis-python/actions/workflows/ci.yml/badge.svg)](https://github.com/Nikkat-Afrin/climate-change-analysis-python/actions/workflows/ci.yml) ![Python](https://img.shields.io/badge/Python-3.12-blue) ![GeoPandas](https://img.shields.io/badge/GeoPandas-maps-green) ![Type](https://img.shields.io/badge/Type-Multi--dataset%20EDA%20%2B%20Stats-orange)
 [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## ❓ Research question
> How do **CO₂ concentrations, surface temperature, and sea-level rise** interact, and how do they relate to the **frequency of climate-related disasters**?

## 📊 Datasets (4 sources, merged on year)
All bundled in [`data/`](data/) so the project is self-contained and reproducible:

| Dataset | Source | File |
|---|---|---|
| Annual mean surface temperature change | IMF Climate Change Indicators | `surface_temperature.csv` |
| Atmospheric CO₂ concentration | NOAA/IMF (atmospheric CO₂) | `atmospheric_co2.csv` |
| Change in mean sea levels | **IMF Climate Change Indicators** (re-sourced from the IMF ArcGIS Hub) | `mean_sea_levels.csv` |
| Climate-related disaster frequency | IMF Climate Indicators **ArcGIS FeatureServer** | `disaster_frequency.geojson` |

> A country-boundary layer (`naturalearth_lowres.geojson`) is bundled for the world maps, replacing the dataset that newer GeoPandas removed.

## 🔬 Methodology
- **Reshaping & cleaning** - `pd.melt` of wide year-columns to tidy long format; per-country/year aggregation; missing-data handling.
- **Exploratory analysis** - univariate & bivariate views of temperature, CO₂, sea level, and disasters; hottest/coolest countries; temporal trends.
- **Geospatial visualization** - **GeoPandas** world maps highlighting the most disaster-prone and temperature-extreme countries (joined to country boundaries by ISO-3 code).
- **Multivariate analysis** - merge all four indicators by **Year**, examine correlations, and fit **polynomial / linear trend regressions** (with cross-validation) of CO₂ ↔ temperature ↔ sea-level relationships.

## 📈 What the analysis shows
- **CO₂, temperature, and sea level rise together** over the study period - strong positive co-movement consistent with the climate-science consensus.
- **Disaster frequency trends upward** alongside warming, with the United States among the most disaster-affected countries in the data.
- The merged yearly view makes the **joint trajectory** of the four indicators visible in a single analysis - the project's main contribution.

> 📓 The full analysis is in [`notebooks/climate_co2_temp_sealevel.ipynb`](notebooks/climate_co2_temp_sealevel.ipynb) (a comprehensive team EDA - it is computation-heavy with several large GeoPandas maps, so allow a few minutes to run end-to-end).

## 🔧 Reproducibility fixes applied
- Repointed all reads to **bundled local data** (the original teammate URLs included one that went 404; sea-level data was **re-sourced from the authoritative IMF ArcGIS Hub**).
- Replaced the removed `geopandas.datasets.get_path('naturalearth_lowres')` with a bundled boundary file.
- Added `returnGeometry=false` to the disaster ArcGIS query so the wide→long melt no longer duplicates polygon geometry (which otherwise exploded memory).

## ▶️ How to run
```bash
pip install -r requirements.txt
jupyter lab notebooks/climate_co2_temp_sealevel.ipynb
```

## 🛠️ Tech stack
`Python` · `pandas` · `GeoPandas` · `scikit-learn` (PolynomialFeatures, LinearRegression, cross-val) · `Matplotlib` · `Seaborn` · `requests`

## 🚀 Future improvements
- Lag/Granger-style analysis of CO₂ → temperature → sea-level timing.
- Interactive choropleths (Plotly/Folium); per-region disaster-trend modeling.

---
*Academic team project (DAV 5400 Final). Data © IMF Climate Change Indicators / NOAA. Original analysis cleaned, re-sourced, and made self-contained.*


## 🏗️ ETL pipeline (`src/climate_etl.py`)

The three IMF Climate-Data-Portal exports each arrive in a different layout (monthly rows, per-sea satellite passes, and a wide one-column-per-year table). The ETL module turns them into one analysis-ready annual table with explicit data-quality gates:

```bash
python src/climate_etl.py            # -> data/processed/climate_annual.csv (year, co2_ppm, temp_anomaly_c, sea_level_mm)
python src/climate_etl.py --strict   # fail (exit non-zero) on any data-quality warning
pytest tests/                        # 10 ETL tests, run in CI on every push
```

Data-quality behaviors worth noting:
- **Indicator disambiguation** - the CO₂ export interleaves ppm concentrations with year-on-year % change rows; only `Parts Per Million` rows are aggregated.
- **Quarantine** - physically implausible raw readings are dropped and logged before aggregation (the 2023 export ends with a corrupt `2024M01,0.68` row, which the pipeline catches).
- **Fair sea-level averaging** - satellite passes are averaged per sea per year *before* the global mean, so heavily-sampled seas don't dominate.
- **Continuity + range checks** - missing years and out-of-range values are reported in a JSON DQ report; `--strict` turns warnings into failures for use in scheduled jobs.


## 🌡️ Interactive dashboard

**Live: <https://nikkat-afrin.github.io/climate-change-analysis-python/>** - KPI cards plus four interactive views (CO₂ + temperature dual-axis timeline, satellite-era sea-level trend, decade-average warming, CO₂-temperature coupling), built straight from the ETL pipeline's output. Regenerate with `python src/build_dashboard.py`.

## 📎 Provenance

This repo absorbed the original course repository (`environmental-impact-analysis`, now archived): the project proposal notebook lives at `notebooks/project_proposal.ipynb` and the original course deck at `reports/course_final_presentation.pptx`.
