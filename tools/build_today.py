#!/usr/bin/env python3
"""
Builds today.json for the TODAY IN SXM banner.

Run daily by .github/workflows/daily.yml. Everything date-driven is computed
here; the browser only handles what needs the current clock (next bridge
opening, crowd window) plus the live weather and marine fetches.

Emits state keys only. Wording lives in copy.json.
"""
from __future__ import annotations
import json, datetime as dt, sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import sxm_logic as L
import sargassum_sir

ROOT = pathlib.Path(__file__).resolve().parent.parent
TZ = dt.timezone(dt.timedelta(hours=-4))          # Atlantic Standard, no DST


def ships_for(day: dt.date) -> tuple[list, int, bool]:
    """Returns (arrivals, pax, known). `known` is False when the date falls
    outside ships.json's coverage - a gap we must not report as a quiet day."""
    try:
        data = json.loads((ROOT / "ships.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [], 0, False
    arrivals = data.get("arrivals", [])
    dates = [a.get("date") for a in arrivals if a.get("date")]
    if not dates:
        return [], 0, False
    iso = day.isoformat()
    known = min(dates) <= iso <= max(dates)
    todays = [a for a in arrivals if a.get("date") == iso]
    return todays, sum(a.get("pax", 0) or 0 for a in todays), known


DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def specials_for(day: dt.date, band: str) -> dict:
    """Recurring weekly items by area. Hand-maintained, never scraped."""
    try:
        data = json.loads((ROOT / "specials.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    key, out = DAYS[day.weekday()], {}
    md = day.strftime("%m-%d")
    for area, v in data.get("areas", {}).items():
        cw = v.get("closed_window")
        if cw:
            a, b = cw
            shut = (a <= md <= b) if a <= b else (md >= a or md <= b)
            if shut:
                continue               # venue closed for the off-season
        items = list(v.get(key, [])) + list(v.get("daily", []))
        if items:
            out[area] = items
    return out


def build(day: dt.date | None = None, fetch_sargassum: bool = True) -> dict:
    day = day or dt.datetime.now(TZ).date()
    band = L.season_band(day)
    in_port, pax, ships_known = ships_for(day)

    # Satellite read of the water. Returns None on any failure, in which case
    # sargassum_state falls back to the calendar and says so.
    sir = sargassum_sir.observe(day) if fetch_sargassum else None

    sev = L.severity(band, pax)
    anom_key, ratio = L.anomaly(pax, day.month)

    slots: list[str] = []

    if not ships_known:
        # No schedule for this date. Say nothing about traffic rather than
        # claim a quiet day we cannot vouch for.
        slots.append("TRAFFIC_DATA_STALE")
    elif pax == 0 and sev in ("BUSY", "CONGESTED", "GRIDLOCK"):
        # The case the old logic could not express: quiet port, busy island.
        slots.append("TRAFFIC_ZERO_SHIPS_STILL_BUSY")
    else:
        slots.append(f"TRAFFIC_{sev}")

    if ships_known and anom_key in ("BELOW_NORMAL", "HEAVIER_THAN_USUAL", "EXCEPTIONAL_FOR_SEASON"):
        slots.append("ANOMALY_" + anom_key.replace("_FOR_SEASON", "")
                                        .replace("HEAVIER_THAN_USUAL", "HEAVIER"))

    sarg = L.sargassum_state(sir, day.month)
    slots.append(sarg)
    specials = specials_for(day, band)
    if specials:
        slots.append("SPECIALS_WEEKLY")
        if band in ("LOW", "DEAD", "SHOULDER_FALL"):
            slots.append("SPECIALS_LOW_SEASON_CAVEAT")
    slots += L.events(day)
    slots += L.closures(band)

    return {
        "generated": dt.datetime.now(TZ).isoformat(timespec="seconds"),
        "date": day.isoformat(),
        "season": band,
        "traffic": {
            "severity": sev if ships_known else None,
            "ships_known": ships_known,
            "cruise_pax": pax,
            "ship_count": len(in_port),
            "ships": [{"ship": a.get("ship"), "line": a.get("line"),
                       "pax": a.get("pax"), "time": a.get("time")} for a in in_port],
            "expected_pax_for_month": L.T["expected_pax"][str(day.month)],
            "anomaly": anom_key if ships_known else None,
            "anomaly_ratio": ratio if ships_known else None,
        },
        "sargassum": sarg,
        "sargassum_observed": sir,                       # None when unreachable
        "sargassum_by_beach": L.sargassum_beach_risk(sir),
        "events": L.events(day),
        "closures": L.closures(band),
        "specials": specials,
        "slots": slots,                       # pre-resolution; client adds live ones
        "beaches": {
            "crowd": L.crowd_lists(),
            "aspect": L.BEACHES,              # client applies live swell to this
        },
        "bridges": {
            "schedule": L.T["bridges"],
            "closure_minutes": L.T["bridge_closure_minutes"],
            "compound_windows": L.T["bridge_compound_windows"],
        },
        "crowd_window": L.T["crowd_window"],
        "swell_config": L.T["swell"],
    }


if __name__ == "__main__":
    day = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else None
    out = build(day)
    (ROOT / "today.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    t = out["traffic"]
    print(f"today.json  {out['date']}  {out['season']}  "
          f"{t['ship_count']} ships / {t['cruise_pax']:,} pax  "
          f"-> {t['severity']} + {t['anomaly']} ({t['anomaly_ratio']}x)")
    s = out["sargassum_observed"]
    if s:
        print(f"sargassum   {out['sargassum']}  (SIR {s['observed_date']}, "
              f"{s['days_old']}d old, windward={s['windward_max']} leeward={s['leeward_max']})")
    else:
        print(f"sargassum   {out['sargassum']}  (SIR unreachable - calendar fallback)")
    print("slots:", ", ".join(out["slots"]))
