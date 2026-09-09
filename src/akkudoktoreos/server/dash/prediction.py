from typing import Optional, Union

import pandas as pd
import requests
from bokeh.models import ColumnDataSource, LinearAxis, Range1d
from bokeh.plotting import figure
from monsterui.franken import Div, FT, Grid, P

from akkudoktoreos.core.pydantic import PydanticDateTimeSeries
from akkudoktoreos.server.dash.bokeh import Bokeh, bokey_apply_theme_to_plot
from akkudoktoreos.server.dash.components import Error

# bar width for 15 minutes bars (time given in millseconds)
BAR_WIDTH_15MIN = 1000 * 60 * 15


def PVForecast(predictions: pd.DataFrame, config: dict, date_time_tz: str, dark: bool) -> FT:
    source = ColumnDataSource(predictions)
    provider = config["pvforecast"]["provider"]

    plot = figure(
        x_axis_type="datetime",
        title=f"PV Power Prediction ({provider})",
        x_axis_label=f"Datetime [localtime {date_time_tz}]",
        y_axis_label="Power [W]",
        sizing_mode="stretch_width",
        height=400,
    )
    plot.vbar(
        x="date_time",
        top="pvforecast_ac_power",
        source=source,
        width=BAR_WIDTH_15MIN * 0.8,
        legend_label="AC Power",
        color="lightblue",
    )
    plot.toolbar.autohide = True
    bokey_apply_theme_to_plot(plot, dark)

    return Bokeh(plot)


def ElectricityPriceForecast(
    predictions: pd.DataFrame, config: dict, date_time_tz: str, dark: bool
) -> FT:
    source = ColumnDataSource(predictions)
    provider = config["elecprice"]["provider"]

    plot = figure(
        x_axis_type="datetime",
        y_range=Range1d(
            predictions["elecprice_marketprice_kwh"].min() - 0.1,
            predictions["elecprice_marketprice_kwh"].max() + 0.1,
        ),
        title=f"Electricity Price Prediction ({provider})",
        x_axis_label=f"Datetime [localtime {date_time_tz}]",
        y_axis_label="Price [Amt./kWh]",
        sizing_mode="stretch_width",
        height=400,
    )
    plot.vbar(
        x="date_time",
        top="elecprice_marketprice_kwh",
        source=source,
        width=BAR_WIDTH_15MIN * 0.8,
        legend_label="Market Price",
        color="lightblue",
    )
    plot.toolbar.autohide = True
    bokey_apply_theme_to_plot(plot, dark)

    return Bokeh(plot)


def WeatherTempAirHumidityForecast(
    predictions: pd.DataFrame, config: dict, date_time_tz: str, dark: bool
) -> FT:
    source = ColumnDataSource(predictions)
    provider = config["weather"]["provider"]

    plot = figure(
        x_axis_type="datetime",
        title=f"Air Temperature and Humidity Prediction ({provider})",
        x_axis_label=f"Datetime [localtime {date_time_tz}]",
        y_axis_label="Temperature [°C]",
        sizing_mode="stretch_width",
        height=400,
    )
    # Add secondary y-axis for humidity
    plot.extra_y_ranges["humidity"] = Range1d(start=-5, end=105)
    y2_axis = LinearAxis(y_range_name="humidity", axis_label="Relative Humidity [%]")
    y2_axis.axis_label_text_color = "green"
    plot.add_layout(y2_axis, "left")

    plot.line(
        "date_time", "weather_temp_air", source=source, legend_label="Air Temperature", color="blue"
    )
    plot.line(
        "date_time",
        "weather_relative_humidity",
        source=source,
        legend_label="Relative Humidity [%]",
        color="green",
        y_range_name="humidity",
    )
    plot.toolbar.autohide = True
    bokey_apply_theme_to_plot(plot, dark)

    return Bokeh(plot)


def WeatherIrradianceForecast(
    predictions: pd.DataFrame, config: dict, date_time_tz: str, dark: bool
) -> FT:
    source = ColumnDataSource(predictions)
    provider = config["weather"]["provider"]

    plot = figure(
        x_axis_type="datetime",
        title=f"Irradiance Prediction ({provider})",
        x_axis_label=f"Datetime [localtime {date_time_tz}]",
        y_axis_label="Irradiance [W/m2]",
        sizing_mode="stretch_width",
        height=400,
    )
    plot.line(
        "date_time",
        "weather_ghi",
        source=source,
        legend_label="Global Horizontal Irradiance",
        color="red",
    )
    plot.line(
        "date_time",
        "weather_dni",
        source=source,
        legend_label="Direct Normal Irradiance",
        color="green",
    )
    plot.line(
        "date_time",
        "weather_dhi",
        source=source,
        legend_label="Diffuse Horizontal Irradiance",
        color="blue",
    )
    plot.toolbar.autohide = True
    bokey_apply_theme_to_plot(plot, dark)

    return Bokeh(plot)


def LoadForecast(predictions: pd.DataFrame, config: dict, date_time_tz: str, dark: bool) -> FT:
    """Render a load forecast for both standard-profile and Cerbo-history providers."""
    source = ColumnDataSource(predictions)
    provider = config["load"]["provider"]
    if provider == "LoadAkkudoktorAdjusted":
        year_energy = config["load"]["loadakkudoktor"]["loadakkudoktor_year_energy_kwh"]
        provider = f"{provider}, {year_energy} kWh"

    plot = figure(
        title=f"Load Prediction ({provider})",
        x_axis_type="datetime",
        x_axis_label=f"Datetime [localtime {date_time_tz}]",
        y_axis_label="Load [W]",
        sizing_mode="stretch_width",
        height=400,
    )
    plot.line(
        "date_time",
        "loadforecast_power_w",
        source=source,
        legend_label="Load forecast",
        color="red",
    )

    # The Akkudoktor profile provider exposes additional mean/stddev series.  A local Cerbo
    # history forecast intentionally only needs the common loadforecast_power_w series.
    if _has_columns(predictions, "loadakkudoktor_mean_power_w"):
        plot.line(
            "date_time",
            "loadakkudoktor_mean_power_w",
            source=source,
            legend_label="Load mean value",
            color="blue",
        )
    if _has_columns(predictions, "loadakkudoktor_std_power_w"):
        stddev_min = predictions["loadakkudoktor_std_power_w"].min()
        stddev_max = predictions["loadakkudoktor_std_power_w"].max()
        if pd.notna(stddev_min) and pd.notna(stddev_max):
            plot.extra_y_ranges["stddev"] = Range1d(start=stddev_min - 5, end=stddev_max + 5)
            y2_axis = LinearAxis(y_range_name="stddev", axis_label="Load Standard Deviation [W]")
            y2_axis.axis_label_text_color = "green"
            plot.add_layout(y2_axis, "left")
            plot.line(
                "date_time",
                "loadakkudoktor_std_power_w",
                source=source,
                legend_label="Load standard deviation",
                color="green",
                y_range_name="stddev",
            )

    plot.toolbar.autohide = True
    bokey_apply_theme_to_plot(plot, dark)
    return Bokeh(plot)


def _has_columns(predictions: pd.DataFrame, *columns: str) -> bool:
    return all(column in predictions.columns for column in columns)


def Prediction(eos_host: str, eos_port: Union[str, int], data: Optional[dict] = None) -> Div:
    """Render all prediction data that is actually available.

    Electricity-price and load forecasts are optional for the Synology/Victron
    prediction-only setup. Missing optional prediction keys therefore no longer
    make the complete prediction dashboard fail.
    """
    server = f"http://{eos_host}:{eos_port}"

    dark = False
    if data and data.get("dark", None) == "true":
        dark = True

    # ---------------------------------------------------------------------
    # Get configuration
    # ---------------------------------------------------------------------
    try:
        result = requests.get(f"{server}/v1/config", timeout=10)
        result.raise_for_status()
    except requests.exceptions.RequestException as err:
        detail = ""
        try:
            detail = result.json().get("detail", "")
        except Exception:
            pass
        return Div(Error(f"Can not retrieve configuration from {server}: {err}, {detail}"))
    config = result.json()

    # ---------------------------------------------------------------------
    # Describe how every prediction should be retrieved.
    # ---------------------------------------------------------------------
    prediction_requests = [
        ("pvforecast_ac_power", "first", "ffill"),
        ("elecprice_marketprice_kwh", "first", "ffill"),
        ("weather_relative_humidity", "mean", "linear"),
        ("weather_temp_air", "mean", "linear"),
        ("weather_ghi", "mean", "linear"),
        ("weather_dni", "mean", "linear"),
        ("weather_dhi", "mean", "linear"),
        ("loadforecast_power_w", "first", "ffill"),
        ("loadakkudoktor_std_power_w", "first", "ffill"),
        ("loadakkudoktor_mean_power_w", "first", "ffill"),
    ]

    # ---------------------------------------------------------------------
    # Fetch every series independently. A missing key is optional here.
    # ---------------------------------------------------------------------
    series_list = []
    missing_keys: list[str] = []

    for key, resample_method, fill_method in prediction_requests:
        params = {
            "key": key,
            "interval": "15 minutes",
            "processing": "resampled",
            "resample_method": resample_method,
            "fill_method": fill_method,
        }

        try:
            result = requests.get(
                f"{server}/v1/prediction/series",
                params=params,
                timeout=10,
            )
            if result.status_code == 404:
                missing_keys.append(key)
                continue
            result.raise_for_status()
            series = PydanticDateTimeSeries(**result.json()).to_series().rename(key)
            series_list.append(series)
        except requests.exceptions.RequestException as err:
            return Div(Error(f"Can not retrieve prediction '{key}' from {server}: {err}"))
        except Exception as err:
            return Div(Error(f"Can not process prediction '{key}' from {server}: {err}"))

    if not series_list:
        return Div(
            P(
                "Noch keine Prognosedaten vorhanden. EOS sammelt bzw. berechnet die erste Prognose; "
                "bitte in einigen Minuten erneut öffnen.",
                cls="p-4 text-center",
            )
        )

    # ---------------------------------------------------------------------
    # Merge into dataframe
    # ---------------------------------------------------------------------
    predictions = pd.concat(series_list, axis=1).reset_index()
    predictions.rename(columns={"index": "date_time"}, inplace=True)

    # Remove time offset from UTC to get naive local time and make bokeh plot in local time
    date_time_tz = predictions["date_time"].dt.tz
    predictions["date_time"] = pd.to_datetime(predictions["date_time"]).dt.tz_localize(None)

    cards: list[FT] = []
    if _has_columns(predictions, "pvforecast_ac_power"):
        cards.append(PVForecast(predictions, config, date_time_tz, dark))
    if _has_columns(predictions, "weather_temp_air", "weather_relative_humidity"):
        cards.append(WeatherTempAirHumidityForecast(predictions, config, date_time_tz, dark))
    if _has_columns(predictions, "weather_ghi", "weather_dni", "weather_dhi"):
        cards.append(WeatherIrradianceForecast(predictions, config, date_time_tz, dark))
    if _has_columns(predictions, "elecprice_marketprice_kwh"):
        cards.append(ElectricityPriceForecast(predictions, config, date_time_tz, dark))
    if _has_columns(predictions, "loadforecast_power_w"):
        cards.append(LoadForecast(predictions, config, date_time_tz, dark))

    notices = []
    if "elecprice_marketprice_kwh" in missing_keys:
        notices.append("Strompreisprognose ist nicht konfiguriert.")
    if "loadforecast_power_w" in missing_keys:
        notices.append(
            "Verbrauchsprognose sammelt noch Cerbo-Lastdaten oder ist nicht konfiguriert."
        )
    if "pvforecast_ac_power" in missing_keys:
        notices.append("Die erste PV-Prognose ist noch nicht verfügbar.")

    info = P(" ".join(notices), cls="text-sm opacity-70 mb-4") if notices else None

    return Div(
        info,
        Grid(*cards, cols_max=2) if cards else P("Noch keine darstellbaren Prognosedaten vorhanden."),
        cls="space-y-4",
    )
