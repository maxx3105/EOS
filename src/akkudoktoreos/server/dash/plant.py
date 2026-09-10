"""Compact Victron plant overview for the Synology prediction-only setup."""

from __future__ import annotations

from typing import Optional, Union

import pandas as pd
import requests
from bokeh.plotting import figure
from fasthtml.common import H2, H3, Script
from monsterui.franken import Div, FT, Grid, P

from akkudoktoreos.core.pydantic import PydanticDateTimeSeries
from akkudoktoreos.server.dash.bokeh import Bokeh, bokey_apply_theme_to_plot
from akkudoktoreos.server.dash.components import Error


PV_DC_KEY = "victron_pv_dc_power_w"
PV_AC_OUT_KEY = "victron_pv_ac_out_power_w"
PV_TOTAL_KEY = "victron_pv_total_power_w"
SITE_LOAD_KEY = "victron_site_load_power_w"
HOUSE_NON_EV_KEY = "victron_house_non_ev_power_w"
EV_KEY = "victron_ev_power_w"
BATTERY_POWER_KEY = "victron_battery_power_w"
GRID_POWER_KEY = "victron_grid_power_w"
BATTERY_SOC_KEY = "battery1-soc-factor"
ZERO_EXPORT_TOLERANCE_W = 50.0


def _format_power(value: Optional[float]) -> str:
    if value is None or pd.isna(value):
        return "–"
    value = float(value)
    if abs(value) < 1000.0:
        return f"{value:.0f} W"
    return f"{value / 1000.0:.2f} kW"


def _battery_text(value: Optional[float]) -> str:
    if value is None or pd.isna(value):
        return "–"
    value = float(value)
    if value > 50.0:
        return f"{_format_power(abs(value))} Laden"
    if value < -50.0:
        return f"{_format_power(abs(value))} Entladen"
    return f"{_format_power(value)} Bereit"


def _grid_text(value: Optional[float]) -> tuple[str, str, bool]:
    """Return display value, status text and whether instantaneous export is notable."""
    if value is None or pd.isna(value):
        return "–", "Keine aktuelle Netzmessung", False
    value = float(value)
    if value < -ZERO_EXPORT_TOLERANCE_W:
        return (
            f"{_format_power(abs(value))} Einspeisung",
            "Momentane Rückspeisung – Nulleinspeisung prüfen",
            True,
        )
    if value < 0.0:
        return f"{_format_power(abs(value))} Einspeisung", "Nulleinspeisung ✓ (Toleranz)", False
    return f"{_format_power(value)} Bezug", "Nulleinspeisung ✓", False


def _latest(series: pd.Series) -> Optional[float]:
    if series.empty:
        return None
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return None
    return float(values.iloc[-1])


def _raw_surplus(pv_forecast: pd.Series, load_forecast: pd.Series) -> pd.Series:
    """PV surplus before battery and EV decisions, aligned on common forecast slots."""
    aligned = pd.concat(
        [pv_forecast.rename("pv"), load_forecast.rename("load")], axis=1, join="inner"
    ).dropna()
    if aligned.empty:
        return pd.Series(dtype=float, name="raw_surplus")
    return (aligned["pv"].astype(float) - aligned["load"].astype(float)).clip(lower=0.0).rename(
        "raw_surplus"
    )


def _series_energy_kwh(series: pd.Series, fallback_interval_minutes: float = 15.0) -> float:
    if series.empty:
        return 0.0
    if len(series.index) > 1:
        index = pd.DatetimeIndex(series.index).sort_values()
        delta_hours = float(index.to_series().diff().dropna().dt.total_seconds().median()) / 3600.0
        if not pd.notna(delta_hours) or delta_hours <= 0:
            delta_hours = fallback_interval_minutes / 60.0
    else:
        delta_hours = fallback_interval_minutes / 60.0
    return float(pd.to_numeric(series, errors="coerce").fillna(0.0).sum()) * delta_hours / 1000.0


def _fetch_series(
    server: str,
    endpoint: str,
    key: str,
    *,
    params: Optional[dict[str, str]] = None,
) -> tuple[pd.Series, Optional[str]]:
    query: dict[str, str] = {"key": key}
    if params:
        query.update(params)
    try:
        result = requests.get(f"{server}{endpoint}", params=query, timeout=10)
        if result.status_code == 404:
            return pd.Series(dtype=float, name=key), None
        result.raise_for_status()
        series = PydanticDateTimeSeries(**result.json()).to_series().rename(key)
        return series, None
    except requests.exceptions.RequestException as err:
        return pd.Series(dtype=float, name=key), f"{key}: {err}"
    except Exception as err:
        return pd.Series(dtype=float, name=key), f"{key}: {err}"


def _plot_index(series: pd.Series) -> pd.Series:
    """Use naive local wall-clock time, matching the existing EOS prediction plots."""
    if series.empty:
        return series
    result = series.copy()
    index = pd.DatetimeIndex(result.index)
    if index.tz is not None:
        index = index.tz_localize(None)
    result.index = index
    return result


def _stat_card(title: str, value: str, subtitle: str, *, warning: bool = False) -> Div:
    return Div(
        P(title, cls="text-sm font-semibold opacity-70"),
        H3(value, cls="text-2xl font-bold mt-1"),
        P(
            subtitle,
            cls=("text-sm mt-2 text-red-700 font-semibold" if warning else "text-sm mt-2 opacity-70"),
        ),
        cls="border rounded-lg p-4 min-h-28",
    )


def _pv_chart(
    dc: pd.Series,
    ac_out: pd.Series,
    total: pd.Series,
    pv_forecast: pd.Series,
    *,
    dark: bool,
) -> FT:
    plot = figure(
        x_axis_type="datetime",
        title="PV Ist & Prognose",
        x_axis_label="Zeit",
        y_axis_label="Leistung [W]",
        sizing_mode="stretch_width",
        height=360,
    )
    if not dc.empty:
        data = _plot_index(dc)
        plot.line(data.index, data.values, legend_label="SmartSolar DC", line_width=2)
    if not ac_out.empty:
        data = _plot_index(ac_out)
        plot.line(data.index, data.values, legend_label="Hoymiles AC-out", line_width=2)
    if not total.empty:
        data = _plot_index(total)
        plot.line(data.index, data.values, legend_label="PV gesamt Ist", line_width=3)
    if not pv_forecast.empty:
        data = _plot_index(pv_forecast)
        plot.line(
            data.index,
            data.values,
            legend_label="PV gesamt Prognose",
            line_width=2,
            line_dash="dashed",
        )
    plot.y_range.start = 0
    plot.legend.click_policy = "hide"
    plot.toolbar.autohide = True
    bokey_apply_theme_to_plot(plot, dark)
    return Bokeh(plot)


def _flow_chart(
    house: pd.Series,
    ev: pd.Series,
    battery: pd.Series,
    grid: pd.Series,
    *,
    dark: bool,
) -> FT:
    plot = figure(
        x_axis_type="datetime",
        title="Energiefluss – letzte 24 Stunden",
        x_axis_label="Zeit",
        y_axis_label="Leistung [W]",
        sizing_mode="stretch_width",
        height=360,
    )
    for series, label in (
        (house, "Hausverbrauch ohne EV"),
        (ev, "EVCS gesamt"),
        (battery, "Batterie (+ Laden / − Entladen)"),
        (grid, "Netz (+ Bezug / − Einspeisung)"),
    ):
        if series.empty:
            continue
        data = _plot_index(series)
        plot.line(data.index, data.values, legend_label=label, line_width=2)
    plot.line([pd.Timestamp.now().tz_localize(None)], [0], line_alpha=0)
    plot.legend.click_policy = "hide"
    plot.toolbar.autohide = True
    bokey_apply_theme_to_plot(plot, dark)
    return Bokeh(plot)


def _forecast_chart(
    pv_forecast: pd.Series,
    load_forecast: pd.Series,
    surplus: pd.Series,
    *,
    dark: bool,
) -> FT:
    plot = figure(
        x_axis_type="datetime",
        title="48-h-Prognose & verfügbarer PV-Rohüberschuss",
        x_axis_label="Zeit",
        y_axis_label="Leistung [W]",
        sizing_mode="stretch_width",
        height=360,
    )
    for series, label, dash in (
        (pv_forecast, "PV-Prognose", "solid"),
        (load_forecast, "Hausverbrauch ohne EV – Prognose", "solid"),
        (surplus, "PV-Rohüberschuss vor Batterie/EV", "dashed"),
    ):
        if series.empty:
            continue
        data = _plot_index(series)
        plot.line(data.index, data.values, legend_label=label, line_width=2, line_dash=dash)
    plot.y_range.start = 0
    plot.legend.click_policy = "hide"
    plot.toolbar.autohide = True
    bokey_apply_theme_to_plot(plot, dark)
    return Bokeh(plot)


def Plant(eos_host: str, eos_port: Union[str, int], data: Optional[dict] = None) -> Div:
    """Render live Victron telemetry together with the forecast that drives future decisions."""
    server = f"http://{eos_host}:{eos_port}"
    dark = bool(data and data.get("dark") == "true")

    try:
        result = requests.get(f"{server}/v1/config", timeout=10)
        result.raise_for_status()
        config = result.json()
    except requests.exceptions.RequestException as err:
        return Div(Error(f"Can not retrieve configuration from {server}: {err}"))

    now = pd.Timestamp.now(tz="UTC")
    history_start = now - pd.Timedelta(hours=24)
    measurement_params = {
        "start_datetime": history_start.isoformat(),
        "end_datetime": (now + pd.Timedelta(minutes=1)).isoformat(),
        "processing": "raw",
    }

    telemetry: dict[str, pd.Series] = {}
    warnings: list[str] = []
    for key in (
        PV_DC_KEY,
        PV_AC_OUT_KEY,
        PV_TOTAL_KEY,
        SITE_LOAD_KEY,
        HOUSE_NON_EV_KEY,
        EV_KEY,
        BATTERY_POWER_KEY,
        GRID_POWER_KEY,
        BATTERY_SOC_KEY,
    ):
        series, warning = _fetch_series(
            server,
            "/v1/measurement/series",
            key,
            params=measurement_params,
        )
        telemetry[key] = series
        if warning:
            warnings.append(warning)

    forecast: dict[str, pd.Series] = {}
    for key in ("pvforecast_ac_power", "loadforecast_power_w"):
        series, warning = _fetch_series(
            server,
            "/v1/prediction/series",
            key,
            params={
                "interval": "15 minutes",
                "processing": "resampled",
                "resample_method": "first",
                "fill_method": "ffill",
            },
        )
        forecast[key] = series
        if warning:
            warnings.append(warning)

    pv_dc = _latest(telemetry[PV_DC_KEY])
    pv_ac_out = _latest(telemetry[PV_AC_OUT_KEY])
    pv_total = _latest(telemetry[PV_TOTAL_KEY])
    house = _latest(telemetry[HOUSE_NON_EV_KEY])
    ev = _latest(telemetry[EV_KEY])
    battery = _latest(telemetry[BATTERY_POWER_KEY])
    battery_soc_factor = _latest(telemetry[BATTERY_SOC_KEY])
    battery_soc = (
        battery_soc_factor * 100.0 if battery_soc_factor is not None else None
    )
    grid = _latest(telemetry[GRID_POWER_KEY])
    grid_value, grid_status, grid_warning = _grid_text(grid)

    newest_timestamps = [
        pd.Timestamp(series.index[-1]) for series in telemetry.values() if not series.empty
    ]
    latest_time = max(newest_timestamps) if newest_timestamps else None
    if latest_time is None:
        freshness = "Noch keine Live-Telemetrie. Nach dem nächsten EOS-Messzyklus erscheinen die Werte."
    else:
        display_time = latest_time
        try:
            timezone = config.get("general", {}).get("timezone")
            if timezone and display_time.tzinfo is not None:
                display_time = display_time.tz_convert(timezone)
        except Exception:
            pass
        freshness = f"Messstand: {display_time.strftime('%d.%m.%Y %H:%M:%S %Z')}"

    pv_forecast = forecast["pvforecast_ac_power"]
    load_forecast = forecast["loadforecast_power_w"]
    surplus = _raw_surplus(pv_forecast, load_forecast)
    surplus_kwh = _series_energy_kwh(surplus)
    surplus_peak_w = float(surplus.max()) if not surplus.empty else None

    cards = [
        _stat_card("SmartSolar DC-PV", _format_power(pv_dc), "4 × Victron SmartSolar MPPT"),
        _stat_card(
            "Hoymiles AC-out-PV",
            _format_power(pv_ac_out),
            "HMS-800W-2T · Ost 90° · 70° · max. 800 W",
        ),
        _stat_card("PV gesamt", _format_power(pv_total), "DC + AC-out über Cerbo GX"),
        _stat_card(
            "Hausverbrauch ohne EV",
            _format_power(house),
            f"Wärmepumpe/Pool enthalten · EV separat {_format_power(ev)}",
        ),
        _stat_card(
            "Batterie",
            _battery_text(battery),
            f"SOC {battery_soc:.0f} % · Inselreserve 15 %" if battery_soc is not None else "SOC – · Inselreserve 15 %",
        ),
        _stat_card("Netz", grid_value, grid_status, warning=grid_warning),
    ]

    if not surplus.empty:
        forecast_summary = P(
            f"48 h PV-Rohüberschuss vor Batterie/EV: ca. {surplus_kwh:.1f} kWh · "
            f"Peak {_format_power(surplus_peak_w)}. Das ist noch keine Ladefreigabe, sondern die "
            "Basis für die spätere Batterie- und EV-Optimierung.",
            cls="border rounded-lg p-3 text-sm",
        )
    elif not pv_forecast.empty:
        forecast_summary = P(
            "PV-Prognose ist vorhanden; die Verbrauchsprognose hat noch keine Werte. "
            "Der PV-Rohüberschuss wird automatisch angezeigt, sobald LoadVictronHistory bereit ist.",
            cls="border rounded-lg p-3 text-sm",
        )
    else:
        forecast_summary = P(
            "Noch keine Prognosedaten verfügbar.",
            cls="border rounded-lg p-3 text-sm",
        )

    notice = (
        P("Einige Reihen konnten nicht gelesen werden: " + " | ".join(warnings), cls="text-sm text-red-700")
        if warnings
        else None
    )

    return Div(
        Div(
            H2("Anlage & Prognose", cls="text-2xl font-bold"),
            P(
                "Read-only Anlagenübersicht aus Cerbo GX und EOS. SmartSolar-DC-PV und "
                "Hoymiles-AC-out werden getrennt dargestellt; die Prognose nutzt weiterhin PV gesamt.",
                cls="text-sm opacity-70 mt-1",
            ),
            P(freshness, cls="text-xs opacity-60 mt-1"),
            cls="mb-4",
        ),
        notice,
        Grid(*cards, cols_max=3),
        forecast_summary,
        Grid(
            _pv_chart(
                telemetry[PV_DC_KEY],
                telemetry[PV_AC_OUT_KEY],
                telemetry[PV_TOTAL_KEY],
                pv_forecast,
                dark=dark,
            ),
            _flow_chart(
                telemetry[HOUSE_NON_EV_KEY],
                telemetry[EV_KEY],
                telemetry[BATTERY_POWER_KEY],
                telemetry[GRID_POWER_KEY],
                dark=dark,
            ),
            cols_max=2,
        ),
        _forecast_chart(pv_forecast, load_forecast, surplus, dark=dark),
        P(
            "Batterie-SOC-Prognose und EV-Ladeempfehlung folgen erst nach Validierung der "
            "PV-/Lastprognose. EOS bleibt bis dahin PREDICTION/read-only.",
            cls="text-xs opacity-60 mt-2",
        ),
        Script("setTimeout(() => window.location.reload(), 60000);"),
        cls="space-y-4",
    )
