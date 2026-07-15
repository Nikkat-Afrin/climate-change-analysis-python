"""Build the interactive climate dashboard (docs/index.html).

Renders the ETL pipeline's analysis-ready annual table into a professional,
self-contained interactive page:

  * KPI header (latest CO2, warming vs baseline, satellite-era sea rise)
  * CO2 + temperature dual-axis timeline
  * sea-level rise with a linear trend fit
  * decade-average warming bars
  * CO2 vs temperature coupling scatter, colored by decade

Run (after `python src/climate_etl.py`):
    python src/build_dashboard.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed" / "climate_annual.csv"
OUT = ROOT / "docs" / "index.html"

CSS = """
 body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 0;
        background: #f4f6f9; color: #1c2733; }
 header { padding: 26px 34px 6px; }
 h1 { margin: 0 0 4px; font-size: 25px; }
 .sub { color: #5c6b7a; font-size: 14px; max-width: 920px; }
 .kpis { display: flex; gap: 14px; padding: 16px 34px 0; flex-wrap: wrap; }
 .kpi { background: white; border-radius: 10px; padding: 12px 20px;
        box-shadow: 0 1px 4px rgba(20,40,80,.08); min-width: 150px; }
 .kpi .v { font-size: 22px; font-weight: 700; }
 .kpi .l { font-size: 12px; color: #5c6b7a; }
 .co2 .v { color: #495057; } .temp .v { color: #d9480f; } .sea .v { color: #1971c2; }
 .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(470px, 1fr));
         gap: 18px; padding: 18px 34px 36px; }
 .card { background: white; border-radius: 10px; padding: 6px;
         box-shadow: 0 1px 4px rgba(20,40,80,.08); }
 .wide { grid-column: 1 / -1; }
 footer { padding: 0 34px 26px; color: #8595a5; font-size: 13px; }
"""


def load() -> pd.DataFrame:
    df = pd.read_csv(DATA)
    return df.sort_values("year").reset_index(drop=True)


def build_figures(df: pd.DataFrame) -> list[go.Figure]:
    figs = []

    # 1 - CO2 + temperature dual axis (wide)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["year"], y=df["co2_ppm"], name="CO₂ (ppm)",
                             line=dict(color="#495057", width=2.5)))
    fig.add_trace(go.Scatter(x=df["year"], y=df["temp_anomaly_c"], name="Temp anomaly (°C)",
                             yaxis="y2", line=dict(color="#d9480f", width=2.5)))
    fig.update_layout(
        title="Atmospheric CO₂ and global temperature anomaly, 1958-2023",
        yaxis=dict(title="CO₂ (ppm)"),
        yaxis2=dict(title="Temp anomaly (°C, vs 1951-80)", overlaying="y", side="right"),
        legend=dict(orientation="h", y=1.12), height=440,
        margin=dict(l=60, r=60, t=70, b=45))
    figs.append(fig)

    # 2 - sea level with trend
    sea = df.dropna(subset=["sea_level_mm"])
    coef = np.polyfit(sea["year"], sea["sea_level_mm"], 1)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=sea["year"], y=sea["sea_level_mm"], mode="markers+lines",
                             name="Observed", line=dict(color="#1971c2")))
    fig.add_trace(go.Scatter(x=sea["year"], y=np.polyval(coef, sea["year"]),
                             name=f"Trend: {coef[0]:.1f} mm/yr",
                             line=dict(dash="dash", color="#e8590c")))
    fig.update_layout(title="Global mean sea-level change (satellite era)",
                      yaxis_title="mm vs reference", height=430,
                      margin=dict(l=55, r=25, t=55, b=45))
    figs.append(fig)

    # 3 - decade warming bars
    d = df.dropna(subset=["temp_anomaly_c"]).copy()
    d["decade"] = (d["year"] // 10) * 10
    dec = d.groupby("decade", as_index=False)["temp_anomaly_c"].mean()
    dec = dec[dec["decade"] >= 1960]
    fig = go.Figure(go.Bar(x=dec["decade"].astype(str) + "s", y=dec["temp_anomaly_c"],
                           marker=dict(color=dec["temp_anomaly_c"], colorscale="OrRd"),
                           text=dec["temp_anomaly_c"].round(2), textposition="outside"))
    fig.update_layout(title="Average temperature anomaly by decade",
                      yaxis_title="°C vs 1951-80", height=430,
                      margin=dict(l=55, r=25, t=55, b=45))
    figs.append(fig)

    # 4 - coupling scatter
    both = df.dropna(subset=["co2_ppm", "temp_anomaly_c"]).copy()
    both["decade"] = ((both["year"] // 10) * 10).astype(str) + "s"
    fig = go.Figure(go.Scatter(
        x=both["co2_ppm"], y=both["temp_anomaly_c"], mode="markers",
        marker=dict(size=9, color=both["year"], colorscale="Viridis",
                    colorbar=dict(title="Year"), line=dict(width=0.5, color="white")),
        text=both["year"].astype(str), hovertemplate="%{text}: %{x:.0f} ppm, %{y:.2f} °C"))
    r = np.corrcoef(both["co2_ppm"], both["temp_anomaly_c"])[0, 1]
    fig.update_layout(title=f"CO₂ vs temperature anomaly (r = {r:.2f})",
                      xaxis_title="CO₂ (ppm)", yaxis_title="Temp anomaly (°C)",
                      height=430, margin=dict(l=55, r=25, t=55, b=45))
    figs.append(fig)
    return figs


def render(figs: list[go.Figure], df: pd.DataFrame) -> str:
    latest_co2 = df.dropna(subset=["co2_ppm"]).iloc[-1]
    latest_t = df.dropna(subset=["temp_anomaly_c"]).iloc[-1]
    sea = df.dropna(subset=["sea_level_mm"])
    rise = sea["sea_level_mm"].iloc[-1] - sea["sea_level_mm"].iloc[0]
    kpis = [
        ("co2", f"{latest_co2['co2_ppm']:.0f} ppm", f"CO₂ in {int(latest_co2['year'])} (was 315 in 1958)"),
        ("temp", f"+{latest_t['temp_anomaly_c']:.2f} °C", f"{int(latest_t['year'])} anomaly vs 1951-80"),
        ("sea", f"+{rise:.0f} mm", f"sea level {int(sea['year'].iloc[0])}-{int(sea['year'].iloc[-1])}"),
        ("co2", f"{len(df)}", "years in the merged dataset"),
    ]
    kpi_html = "".join(
        f'<div class="kpi {c}"><div class="v">{v}</div><div class="l">{l}</div></div>'
        for c, v, l in kpis)
    charts = []
    for i, fig in enumerate(figs):
        cls = "card wide" if i == 0 else "card"
        inner = fig.to_html(full_html=False, include_plotlyjs="cdn" if i == 0 else False,
                            div_id=f"chart-{i}")
        charts.append(f'<div class="{cls}">{inner}</div>')
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Climate Indicators Dashboard</title><style>{CSS}</style></head><body>
<header><h1>Climate Indicators Dashboard</h1>
<div class="sub">CO₂ concentration, global surface-temperature anomaly, and mean sea level,
merged into one analysis-ready annual series by this repo's ETL pipeline
(<code>src/climate_etl.py</code>) with explicit data-quality gates.
Sources: NOAA/Scripps, FAO via IMF Climate Data Portal, NOAA satellite altimetry.</div>
</header>
<div class="kpis">{kpi_html}</div>
<div class="grid">{''.join(charts)}</div>
<footer>Regenerate: <code>python src/climate_etl.py && python src/build_dashboard.py</code></footer>
</body></html>"""


def main() -> None:
    df = load()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(render(build_figures(df), df), encoding="utf-8")
    print(f"Dashboard -> {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
