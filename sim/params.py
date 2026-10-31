"""Physical constants, regulatory minima and cost parameters, each with its source.

Anything marked ASSUMPTION is ours and must appear in the provenance table (A-7).
Everything marked VERIFY was quoted from memory and needs checking before it goes on a slide.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from contracts import WakeCategory as W

# ---------------------------------------------------------------- wake separation
# In-trail radar separation on final approach, nautical miles, (leader, follower).
# Source: FAA JO 7110.65 §5-5-4 wake turbulence minima (legacy categories, not RECAT). VERIFY.
WAKE_SOURCE = "FAA JO 7110.65 §5-5-4 (legacy wake categories)"
MIN_RADAR_SEPARATION_NM = 3.0
WAKE_SEPARATION_NM: dict[tuple[W, W], float] = {
    (W.SUPER, W.SUPER): 4.0, (W.SUPER, W.HEAVY): 6.0, (W.SUPER, W.B757): 7.0,
    (W.SUPER, W.LARGE): 7.0, (W.SUPER, W.SMALL): 8.0,
    (W.HEAVY, W.HEAVY): 4.0, (W.HEAVY, W.B757): 5.0, (W.HEAVY, W.LARGE): 5.0, (W.HEAVY, W.SMALL): 6.0,
    (W.B757, W.SMALL): 4.0,
}
# ASSUMPTION: distance minima converted to time at a typical final-approach groundspeed.
APPROACH_GROUNDSPEED_KT = 140.0


def wake_separation_min(leader: W, follower: W) -> float:
    nm = WAKE_SEPARATION_NM.get((leader, follower), MIN_RADAR_SEPARATION_NM)
    return nm / APPROACH_GROUNDSPEED_KT * 60.0


# ---------------------------------------------------------------- other rule sources
FUEL_SOURCE = ("ICAO Annex 6 Part I §4.3.6.3 final reserve fuel; landing fuel must still cover "
               "the alternate (cf. 14 CFR 121.639)")
DUTY_SOURCE = "14 CFR Part 117 flight duty period limits"
WEATHER_SOURCE = "FAA AC 00-24C thunderstorm avoidance"
SLOT_SOURCE = "FAA Ground Delay Program slot list (ATCSCC)"
CAPACITY_SOURCE = "Airport arrival rate (AAR) set by ATC traffic management"
TAXIWAY_SOURCE = "Airport NOTAM: taxiway closure"
HOLDING_SOURCE = "Sector holding-stack capacity (ATC letter of agreement)"
GATE_SOURCE = "Airport gate plan / gate-use agreement"
CREW_SOURCE = "Ramp labour agreement overtime cap (ASSUMPTION)"

# ASSUMPTION: after a diversion, time until the aircraft is back at the hub and in-block.
DIVERSION_RECOVERY_MIN = 180.0
# ASSUMPTION: taxi-in at an alternate airport.
DIVERSION_TAXI_IN_MIN = 10.0


# ---------------------------------------------------------------- costs
class CostParams(BaseModel):
    """USD cost model. Override fields for sensitivity analysis (D-7)."""
    model_config = ConfigDict(frozen=True)

    # Airline (pilot agent)
    # A4A puts the US aircraft block-minute cost at ~$74/min (2019, VERIFY), fuel included.
    # Fuel is costed separately below, so we use the non-fuel share. ASSUMPTION: ~2/3.
    delay_usd_per_min: float = 50.0
    fuel_usd_per_kg: float = 0.80               # ~$2.50/US gal jet fuel. VERIFY current price.
    missed_connection_usd_per_pax: float = 250.0  # rebooking + care. ASSUMPTION
    turbulence_usd_per_min: float = 20.0        # shadow cost for pax comfort/injury risk. ASSUMPTION
    diversion_fixed_usd: float = 25_000.0       # handling, crew, pax care. ASSUMPTION
    # Ground handler
    ramp_usd_per_crew_min: float = 1.0          # ~$60/h loaded labour. ASSUMPTION
    gate_change_usd: float = 300.0              # re-staffing, pax re-direction. ASSUMPTION
    knock_on_delay_usd_per_min: float = 50.0    # next-leg (turnaround) delay, same rate as delay
    # ATC (shadow costs: ATC pays no money, these encode workload and throughput)
    holding_usd_per_min: float = 30.0           # ASSUMPTION
    reroute_coordination_usd: float = 150.0     # ASSUMPTION
    unused_rbs_slot_usd: float = 300.0          # throughput lost if the RBS slot goes unused. ASSUMPTION
    # Global objective weights per organisation
    weight_atc: float = 1.0
    weight_pilot: float = 1.0
    weight_ground: float = 1.0
    # Physical
    co2_kg_per_kg_fuel: float = 3.16            # ICAO carbon emissions calculator


DEFAULT_COSTS = CostParams()
