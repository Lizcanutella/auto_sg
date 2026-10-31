"""Reads the organiser workbook `challenge2_operational_constraints.xlsx` (A-1).

Every limit used by the scenario builder comes from here unless it is listed in
`OUR_ASSUMPTIONS` (which goes on the "changed / added limits" slide).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import pandas as pd

from contracts import WakeCategory

ROOT = Path(__file__).resolve().parent.parent
WORKBOOK = ROOT / "challenge2_operational_constraints.xlsx"

_WAKE_NAMES = {"super": WakeCategory.SUPER, "heavy": WakeCategory.HEAVY,
               "large": WakeCategory.LARGE, "small": WakeCategory.SMALL}


@dataclass(frozen=True)
class AirportLimits:
    iata: str
    name: str
    size_class: str                  # "Large hub" | "Medium hub" | "Small hub" | "Non-hub"
    active_runways: int
    gates: int
    max_runway_ops_per_hour: float   # arrivals + departures
    min_turnaround_min: float
    spare_gates: int


@dataclass(frozen=True)
class FuelCrewRules:
    final_reserve_min: float         # of holding fuel
    contingency_fraction: float      # of trip fuel
    holding_burn_narrow_kg_h: float
    holding_burn_wide_kg_h: float
    spare_holding_on_arrival_min: float
    crew_max_duty_h: float
    ground_shift_h: float
    overtime_multiplier: float
    gate_change_notice_min: float


@dataclass(frozen=True)
class Workbook:
    airports: dict[str, AirportLimits]
    wake_nm: dict[tuple[WakeCategory, WakeCategory], float]
    wake_default_nm: float
    fuel_crew: FuelCrewRules


def _sheet(path: Path, name: str, first_header: str) -> pd.DataFrame:
    """Sheets start with a free-text note; find the real header row by its first cell."""
    raw = pd.read_excel(path, sheet_name=name, header=None)
    h = raw.index[raw.iloc[:, 0].astype(str).str.strip().eq(first_header)][0]
    return raw.iloc[h + 1:].set_axis([str(c).strip() for c in raw.iloc[h]], axis=1).dropna(how="all")


def _number(text: object) -> float:
    m = re.search(r"\d[\d,]*\.?\d*", str(text))
    if not m:
        raise ValueError(f"no number in {text!r}")
    return float(m.group().replace(",", ""))


def _wake(text: str) -> WakeCategory:
    return _WAKE_NAMES[str(text).split()[0].lower()]


@cache
def load_workbook(path: Path = WORKBOOK) -> Workbook:
    cap = _sheet(path, "airport_capacity", "IATA_CODE")
    airports = {
        r.IATA_CODE: AirportLimits(
            iata=r.IATA_CODE, name=str(r.AIRPORT).replace("\xa0", " "), size_class=r.size_class,
            active_runways=int(r.active_runways), gates=int(r.gates),
            max_runway_ops_per_hour=float(r.max_runway_ops_per_hour),
            min_turnaround_min=float(r.min_turnaround_min), spare_gates=int(r.spare_gates_at_any_time),
        )
        for r in cap.itertuples(index=False)
    }

    wake_rows = _sheet(path, "wake_separation", "leader")
    wake_nm, default_nm = {}, None
    for r in wake_rows.itertuples(index=False):
        leader, follower, nm = r[0], r[1], float(r[2])
        if str(leader).lower().startswith("any other"):
            default_nm = nm
        else:
            wake_nm[(_wake(leader), _wake(follower))] = nm

    fc = {str(r.rule).strip().lower(): r.value for r in _sheet(path, "fuel_and_crew", "rule").itertuples(index=False)}
    shift = str(fc["ground crew shift"])
    fuel_crew = FuelCrewRules(
        final_reserve_min=_number(fc["final fuel reserve"]),
        contingency_fraction=_number(fc["contingency fuel"]) / 100.0,
        holding_burn_narrow_kg_h=_number(fc["holding fuel burn (narrowbody)"]),
        holding_burn_wide_kg_h=_number(fc["holding fuel burn (widebody)"]),
        spare_holding_on_arrival_min=_number(fc["assumed spare fuel on arrival"]),
        crew_max_duty_h=_number(fc["flight crew max duty"]),
        ground_shift_h=_number(shift),
        overtime_multiplier=float(re.search(r"(\d+(?:\.\d+)?)\s*x", shift).group(1)),
        gate_change_notice_min=_number(fc["gate change notice"]),
    )
    return Workbook(airports=airports, wake_nm=wake_nm, wake_default_nm=default_nm, fuel_crew=fuel_crew)


# Limits the workbook does not give, which we had to choose. State all of these in the demo.
OUR_ASSUMPTIONS = {
    "arrival_share_of_runway_ops": (0.5, "half of max_runway_ops_per_hour are arrivals"),
    "arrival_runways": ("max(1, active_runways // 2)", "wake spacing applies per arrival runway stream"),
    "weather_capacity_cut": ("0.15 + WEATHER_DELAY/400, capped at 0.5", "only for rows with WEATHER_DELAY > 15"),
    "cruise_burn": ("= holding burn", "workbook only gives holding burn; trip fuel = planned air time x this"),
    "planned_air_time": ("SCHEDULED_TIME - 20 min", "median taxi-out 14 + taxi-in 6 in flights.csv"),
    "regional_holding_burn": ("narrowbody rate", "workbook has no regional-jet figure"),
    "spare_fuel_reading": ("45 min spare is on top of the 30 min final reserve", "workbook wording is ambiguous"),
    "alternate_fuel": (0, "workbook has no alternate requirement"),
    "max_holding_min": (30, "holding-stack limit per sector"),
    "max_ramp_overtime_min": (60, "cap after which the ground handler cannot staff the turn"),
    "decision_time": ("scheduled departure - 30 min", "pre-departure decision point"),
    "min_connect_min": (35, "minimum connecting time for passengers"),
}
