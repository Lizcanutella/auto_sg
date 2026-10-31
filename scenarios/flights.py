"""Loads `flights.csv` and puts every time on one clock (A-1).

DOT times are local `hhmm` integers: departure at the origin, arrival at the destination.
We build absolute minutes on the DESTINATION clock (day ordinal x 1440 + minutes), using
SCHEDULED_TIME to convert the departure. The arrival day is chosen so the implied
time-zone offset stays within 12 h, which handles arrivals after midnight.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path

import numpy as np
import pandas as pd

from contracts import SizeClass, WakeCategory

ROOT = Path(__file__).resolve().parent.parent
FLIGHTS = ROOT / "flights.csv"

REGIONAL_CARRIERS = {"OO", "EV", "MQ"}   # SkyWest, ExpressJet, Envoy: CRJ/ERJ fleets
WIDEBODY_MIN_DISTANCE_MI = 2500


def hhmm_to_min(x: pd.Series) -> pd.Series:
    x = x.astype("int64")
    return (x // 100) * 60 + x % 100


def aircraft_class(airline: str, distance_mi: float) -> tuple[SizeClass, WakeCategory]:
    """Stated heuristic (no aircraft type in the DOT data)."""
    if airline in REGIONAL_CARRIERS:
        return SizeClass.REGIONAL, WakeCategory.LARGE   # CRJ/ERJ are FAA "Large" for wake
    if distance_mi > WIDEBODY_MIN_DISTANCE_MI:
        return SizeClass.WIDEBODY, WakeCategory.HEAVY
    return SizeClass.NARROWBODY, WakeCategory.LARGE


@cache
def load_flights(path: Path = FLIGHTS) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"TAIL_NUMBER": str, "ORIGIN_AIRPORT": str, "DESTINATION_AIRPORT": str},
                     low_memory=False)
    day = np.array([date(y, m, d).toordinal() for y, m, d in zip(df.YEAR, df.MONTH, df.DAY)], dtype="int64")
    dep_local = hhmm_to_min(df.SCHEDULED_DEPARTURE)
    arr_local = hhmm_to_min(df.SCHEDULED_ARRIVAL)
    sched = df.SCHEDULED_TIME.astype(float)

    # Arrival on the departure day, the next day, or (westbound red-eyes) never earlier.
    offset = (arr_local - sched) - dep_local          # implied destination - origin time-zone offset
    arr_day_shift = np.where(offset < -720, 1, np.where(offset > 720, -1, 0))
    arr_rel = arr_local + 1440 * arr_day_shift          # minutes from midnight of the DOT date, dest clock

    df["day"] = day
    df["date"] = pd.to_datetime(df[["YEAR", "MONTH", "DAY"]]).dt.strftime("%Y-%m-%d")
    df["sched_arr_abs"] = day * 1440 + arr_rel
    df["sched_dep_abs_dest"] = df.sched_arr_abs - sched
    df["sched_dep_abs_origin"] = day * 1440 + dep_local  # origin clock: used for legs departing our airport
    df["landing_abs"] = df.sched_arr_abs + df.ARRIVAL_DELAY.astype(float) - df.TAXI_IN.astype(float)
    df["flight_id"] = df.AIRLINE + df.FLIGHT_NUMBER.astype(str) + "-" + df.date
    df["is_weather"] = df.WEATHER_DELAY > 15
    return df


@dataclass
class FlightIndex:
    """Lookups the builder needs, computed once."""
    df: pd.DataFrame
    arrivals_by_dest: dict[str, pd.DataFrame]   # sorted by landing_abs
    legs_by_tail: dict[str, pd.DataFrame]       # sorted by sched_dep_abs_origin


@cache
def flight_index(path: Path = FLIGHTS) -> FlightIndex:
    df = load_flights(path)
    arrivals = {k: g.sort_values("landing_abs") for k, g in df.groupby("DESTINATION_AIRPORT")}
    legs = {k: g.sort_values("sched_dep_abs_origin") for k, g in df.groupby("TAIL_NUMBER")}
    return FlightIndex(df=df, arrivals_by_dest=arrivals, legs_by_tail=legs)
