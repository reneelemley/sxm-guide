"""Unit tests for the TODAY IN SXM engine. Run: python3 -m unittest discover tools"""
import unittest, datetime as dt, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import sxm_logic as L


class Seasons(unittest.TestCase):
    def test_bands(self):
        cases = [
            (dt.date(2026, 12, 25), "PEAK_HOLIDAY"),
            (dt.date(2027, 1, 3),   "PEAK_HOLIDAY"),
            (dt.date(2026, 2, 14),  "HIGH"),
            (dt.date(2026, 4, 15),  "HIGH"),
            (dt.date(2026, 4, 16),  "SHOULDER_SPRING"),
            (dt.date(2026, 5, 31),  "SHOULDER_SPRING"),
            (dt.date(2026, 7, 4),   "LOW"),
            (dt.date(2026, 9, 15),  "DEAD"),
            (dt.date(2026, 10, 31), "DEAD"),
            (dt.date(2026, 11, 1),  "SHOULDER_FALL"),
            (dt.date(2026, 12, 17), "HIGH"),
        ]
        for d, want in cases:
            self.assertEqual(L.season_band(d), want, d)

    def test_every_day_of_year_resolves(self):
        d = dt.date(2026, 1, 1)
        while d.year == 2026:
            L.season_band(d)
            d += dt.timedelta(days=1)


class Traffic(unittest.TestCase):
    def test_the_case_that_broke_the_old_logic(self):
        """Two mega-ships in August: heavy in absolute terms AND wildly off-season."""
        self.assertEqual(L.severity("LOW", 10000), "CONGESTED")
        key, ratio = L.anomaly(10000, 8)
        self.assertEqual(key, "EXCEPTIONAL_FOR_SEASON")
        self.assertGreater(ratio, 7)

    def test_two_ships_february_is_an_ordinary_day(self):
        self.assertEqual(L.severity("HIGH", 4868), "BUSY")
        key, ratio = L.anomaly(4868, 2)
        self.assertEqual(key, "TYPICAL")
        self.assertLess(ratio, 1)

    def test_no_ships_is_not_automatically_clear(self):
        self.assertEqual(L.severity("PEAK_HOLIDAY", 0), "BUSY")
        self.assertEqual(L.severity("HIGH", 0), "NORMAL")
        self.assertEqual(L.severity("DEAD", 0), "EMPTY")

    def test_severity_never_decreases_as_passengers_rise(self):
        order = ["EMPTY", "QUIET", "NORMAL", "BUSY", "CONGESTED", "GRIDLOCK"]
        for band in L.T["traffic_matrix"]:
            idx = [order.index(s) for s in L.T["traffic_matrix"][band]]
            self.assertEqual(idx, sorted(idx), band)

    def test_high_season_stacks_big_and_small_ships(self):
        """5 ships, 2 mega + 3 small, is a capacity day."""
        self.assertEqual(L.severity("HIGH", 2 * 5500 + 3 * 2200), "GRIDLOCK")


class Events(unittest.TestCase):
    def test_easter(self):
        self.assertEqual(L.easter(2026), dt.date(2026, 4, 5))
        self.assertEqual(L.easter(2027), dt.date(2027, 3, 28))

    def test_the_two_carnivals_never_fire_together(self):
        d = dt.date(2026, 1, 1)
        while d.year == 2026:
            e = L.events(d)
            self.assertFalse(
                "EVENT_FRENCH_CARNIVAL" in e and "EVENT_DUTCH_CARNIVAL" in e, d)
            d += dt.timedelta(days=1)

    def test_french_carnival_is_february_dutch_is_spring(self):
        self.assertIn("EVENT_FRENCH_CARNIVAL", L.events(dt.date(2026, 2, 16)))
        self.assertIn("EVENT_DUTCH_CARNIVAL", L.events(dt.date(2026, 4, 30)))

    def test_abolition_day_is_french_only(self):
        e = L.events(dt.date(2026, 5, 28))
        self.assertIn("EVENT_PUBLIC_HOLIDAY_FRENCH", e)
        self.assertNotIn("EVENT_PUBLIC_HOLIDAY_DUTCH", e)

    def test_kings_day_is_dutch_only(self):
        e = L.events(dt.date(2026, 4, 27))
        self.assertIn("EVENT_PUBLIC_HOLIDAY_DUTCH", e)
        self.assertNotIn("EVENT_PUBLIC_HOLIDAY_FRENCH", e)


class Swell(unittest.TestCase):
    def test_ordinary_trade_state_is_not_an_alert(self):
        """1.5m at 8s from the east is the most common day of the year.
        The old threshold fired on this, which would have trained people to ignore it."""
        self.assertNotIn("NORTH_WEST", L.swell_state(1.5, 80, 8))

    def test_live_reading_4_aug_2026(self):
        self.assertEqual(L.swell_state(0.9, 80, 5), "SWELL_CALM")

    def test_north_swell_is_graded(self):
        self.assertEqual(L.swell_state(1.3, 340, 10), "SWELL_NORTH_WEST_ROUGH")
        self.assertEqual(L.swell_state(2.0, 340, 11), "SWELL_NORTH_WEST_ROUGH")
        self.assertEqual(L.swell_state(2.6, 340, 11), "SWELL_NORTH_WEST_DANGEROUS")

    def test_long_period_alone_is_dangerous(self):
        """1.5m at 13s dumps harder on a steep beach than 2.5m at 7s."""
        self.assertEqual(L.swell_state(1.5, 340, 13), "SWELL_NORTH_WEST_DANGEROUS")

    def test_north_swell_hits_the_leeward_beaches(self):
        b = L.beaches_for("SWELL_NORTH_WEST_ROUGH", 1)
        for x in ("Baie Rouge", "Mullet Bay", "Plum Bay", "Happy Bay"):
            self.assertIn(x, b["rough"], x)
        self.assertIn("Le Galion", b["calm"])
        self.assertIn("Great Bay", b["calm"])

    def test_strong_wind_is_its_own_state(self):
        self.assertEqual(L.swell_state(1.0, 80, 6, wind_kt=24), "SWELL_EAST_WINDY")

    def test_missing_data_is_explicit_not_calm(self):
        self.assertEqual(L.swell_state(None, None, None), "SWELL_DATA_STALE")

    def test_rip_list_names_the_documented_hazards(self):
        b = L.beaches_for("SWELL_CALM", 1)
        for x in ("Mullet Bay", "Guana Bay", "Baie Rouge"):
            self.assertIn(x, b["high_rip"], x)

    def test_wind_spots_improve_in_trades(self):
        self.assertEqual(sorted(L.beaches_for("SWELL_CALM", 1)["wind_spots"]),
                         ["Coconut Grove", "Le Galion"])


class Resolver(unittest.TestCase):
    def test_never_emits_contradictory_traffic(self):
        out = L.resolve(["TRAFFIC_QUIET", "TRAFFIC_GRIDLOCK", "SWELL_CALM"])
        traffic = [s for s in out if s.startswith("TRAFFIC")]
        self.assertEqual(len(traffic), 1)

    def test_caps_the_banner(self):
        many = ["BRIDGE_COMPOUND_PM", "TRAFFIC_BUSY", "ANOMALY_HEAVIER",
                "SWELL_CALM", "SARGASSUM_LIKELY", "CROWD_AVOID_LIST"]
        self.assertLessEqual(len(L.resolve(many)), 3)

    def test_bridge_outranks_traffic(self):
        out = L.resolve(["TRAFFIC_BUSY", "BRIDGE_COMPOUND_PM"], limit=1)
        self.assertEqual(out, ["BRIDGE_COMPOUND_PM"])


class Beaches(unittest.TestCase):
    def test_sargassum_only_flags_east_facing(self):
        b = L.beaches_for("SWELL_CALM", 7)
        self.assertIn("Orient Bay", b["sargassum_risk"])
        self.assertIn("Le Galion", b["sargassum_risk"])
        self.assertNotIn("Baie Rouge", b["sargassum_risk"])

    def test_no_sargassum_in_winter(self):
        self.assertEqual(L.beaches_for("SWELL_CALM", 1)["sargassum_risk"], [])

    def test_crowd_lists_are_disjoint(self):
        c = L.crowd_lists()
        self.assertFalse(set(c["avoid"]) & set(c["escape"]))
        self.assertIn("Maho", c["avoid"])
        self.assertIn("Happy Bay", c["escape"])


if __name__ == "__main__":
    unittest.main(verbosity=2)


class Coverage(unittest.TestCase):
    """A date outside ships.json must not be reported as a quiet day."""
    def test_unknown_date_is_stale_not_quiet(self):
        import build_today
        out = build_today.build(dt.date(2030, 2, 14), fetch_sargassum=False)
        self.assertIn("TRAFFIC_DATA_STALE", out["slots"])
        self.assertFalse(any(s.startswith("TRAFFIC_") and s != "TRAFFIC_DATA_STALE"
                             for s in out["slots"]))
        self.assertIsNone(out["traffic"]["severity"])

    def test_known_date_reports_normally(self):
        import build_today
        out = build_today.build(dt.date(2026, 8, 4), fetch_sargassum=False)
        self.assertTrue(out["traffic"]["ships_known"])
        self.assertIsNotNone(out["traffic"]["severity"])


# ---------------------------------------------------------------- sargassum

import sargassum_sir as S

# Mirrors the real KMZ: LineString placemarks carrying an int risk. Includes
# an Anguilla vertex (lat 18.22) and a St Barths one (lon -62.83) that must be
# rejected, and a St Maarten vertex on each coast.
FIXTURE_KML = """<?xml version="1.0" encoding="utf-8" ?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document id="root_doc">
<Folder><name>Risk_20260803</name>
  <Placemark id="a">
    <ExtendedData><SchemaData><SimpleData name="risk">3</SimpleData></SchemaData></ExtendedData>
    <LineString><coordinates>-63.010,18.098 -63.006,18.086 -63.010,18.045</coordinates></LineString>
  </Placemark>
  <Placemark id="b">
    <ExtendedData><SchemaData><SimpleData name="risk">1</SimpleData></SchemaData></ExtendedData>
    <LineString><coordinates>-63.129,18.073 -63.053,18.104 -63.129,18.043</coordinates></LineString>
  </Placemark>
  <Placemark id="offisland">
    <ExtendedData><SchemaData><SimpleData name="risk">3</SimpleData></SchemaData></ExtendedData>
    <LineString><coordinates>-63.050,18.220 -62.830,17.900</coordinates></LineString>
  </Placemark>
</Folder></Document></kml>"""


class SargassumParsing(unittest.TestCase):
    def test_parses_risk_and_coordinates(self):
        pts = S.parse_kml(FIXTURE_KML)
        self.assertEqual(len(pts), 6)          # 3 + 3, off-island pair dropped
        self.assertEqual({p[2] for p in pts}, {1, 3})

    def test_neighbouring_islands_are_excluded(self):
        """Anguilla sits 12km north and St Barths 25km east. Neither is us."""
        pts = S.parse_kml(FIXTURE_KML)
        self.assertFalse(any(lat > 18.13 for _, lat, _ in pts))
        self.assertFalse(any(lon > -62.95 for lon, _, _ in pts))

    def test_windward_sectors_are_east_and_south(self):
        self.assertEqual(S.sector_of(-63.010, 18.045), "E")     # Dawn Beach
        self.assertEqual(S.sector_of(-63.129, 18.043), "W")     # Mullet Bay
        self.assertEqual(S.sector_of(-63.053, 18.104), "N")     # Grand Case
        self.assertEqual(S.sector_of(-63.048, 18.010), "S")     # Great Bay

    def test_summary_splits_windward_from_leeward(self):
        s = S.summarise(S.parse_kml(FIXTURE_KML))
        self.assertEqual(s["island_max"], 3)
        self.assertEqual(s["windward_max"], 3)
        self.assertEqual(s["leeward_max"], 1)

    def test_empty_input_is_none_not_zero(self):
        """No data must never be reported as a clean beach."""
        self.assertIsNone(S.summarise([]))


class SargassumState(unittest.TestCase):
    def obs(self, wind, lee, days_old=0):
        return {"island_max": max(wind, lee), "windward_max": wind,
                "leeward_max": lee, "days_old": days_old, "sectors": {}}

    def test_split_is_the_useful_state(self):
        """Atlantic fouled, Caribbean clean - the day the banner earns its keep."""
        self.assertEqual(L.sargassum_state(self.obs(3, 1), 7),
                         "SARGASSUM_WINDWARD_ONLY_HIGH")
        self.assertEqual(L.sargassum_state(self.obs(2, 1), 7),
                         "SARGASSUM_WINDWARD_ONLY")

    def test_uniform_island_reports_a_level(self):
        self.assertEqual(L.sargassum_state(self.obs(0, 0), 1), "SARGASSUM_NONE")
        self.assertEqual(L.sargassum_state(self.obs(3, 3), 7), "SARGASSUM_HIGH")

    def test_january_observation_beats_the_calendar(self):
        """The regression that matters. Raw AFAI peaks in Nov-Jan on sun glint
        and whitecaps; the SIR archive reads 0 across every vertex on
        2026-01-15. An observed clean January must never say 'sargassum season'."""
        self.assertEqual(L.sargassum_state(self.obs(0, 0), 1), "SARGASSUM_NONE")

    def test_august_observation_can_say_clean(self):
        """The complaint that started this: a calendar rule shouting in a month
        when the water is actually clear."""
        self.assertEqual(L.sargassum_state(self.obs(0, 0), 8), "SARGASSUM_NONE")

    def test_missing_observation_falls_back_and_admits_it(self):
        for month in range(1, 13):
            state = L.sargassum_state(None, month)
            self.assertTrue(state.endswith("_UNOBSERVED"), state)

    def test_stale_observation_is_not_passed_off_as_fresh(self):
        self.assertEqual(L.sargassum_state(self.obs(3, 3, days_old=4), 7),
                         "SARGASSUM_OBSERVED_STALE")

    def test_observed_and_guessed_states_never_share_a_name(self):
        """Copy must be able to tell a measurement from a guess."""
        guessed = {L.sargassum_calendar(m) for m in range(1, 13)}
        observed = {L.sargassum_state(self.obs(w, l), 7)
                    for w in range(4) for l in range(4)}
        self.assertFalse(guessed & observed)


class SargassumBeaches(unittest.TestCase):
    def obs(self, wind, lee):
        return {"island_max": max(wind, lee), "windward_max": wind,
                "leeward_max": lee, "days_old": 0, "sectors": {}}

    def test_atlantic_beaches_take_the_windward_reading(self):
        risk = L.sargassum_beach_risk(self.obs(3, 0))
        for name in ("Orient Bay", "Dawn Beach", "Guana Bay",
                     "Le Galion", "Coconut Grove", "Oyster Pond"):
            self.assertEqual(risk[name], 3, name)

    def test_caribbean_beaches_take_the_leeward_reading(self):
        risk = L.sargassum_beach_risk(self.obs(3, 0))
        for name in ("Grand Case", "Baie Rouge", "Happy Bay", "Plum Bay",
                     "Friar\'s Bay", "Galisbay", "Cupecoy"):
            self.assertEqual(risk[name], 0, name)

    def test_southwest_beaches_do_not_inherit_southeast_risk(self):
        """The bug this replaced. Mullet Bay, Maho, Simpson Bay, Great Bay and
        Little Bay all face south, so a compass-sector model handed them the
        reading from the southeast corner - eight kilometres away, across the
        island, on the other side of the wind. They are Caribbean water and
        must read as such."""
        risk = L.sargassum_beach_risk(self.obs(3, 0))
        for name in ("Mullet Bay", "Maho", "Simpson Bay", "Kim Sha",
                     "Great Bay", "Little Bay", "Indigo Bay", "Cole Bay"):
            self.assertEqual(risk[name], 0, name)
        self.assertNotEqual(risk["Mullet Bay"], risk["Dawn Beach"])

    def test_no_observation_yields_no_claims(self):
        self.assertEqual(L.sargassum_beach_risk(None), {})

    def test_partial_observation_yields_no_claims(self):
        self.assertEqual(L.sargassum_beach_risk(
            {"windward_max": 3, "leeward_max": None}), {})


class RealNoaaSample(unittest.TestCase):
    """Parses an unmodified slice of NOAA's Risk_20260803.kml.

    Expected values were computed independently in the browser against the
    full 12.7 MB file before this fixture was cut, so a parser bug shows up as
    a mismatch rather than a silently agreeing reimplementation.
    """
    def setUp(self):
        p = pathlib.Path(__file__).parent / "data" / "sir_sample_20260803.kml"
        self.pts = S.parse_kml(p.read_text(encoding="utf-8"))

    def test_vertex_count_matches_independent_count(self):
        self.assertEqual(len(self.pts), 88)

    def test_summary_matches_independent_summary(self):
        s = S.summarise(self.pts)
        self.assertEqual(s["island_max"], 3)
        self.assertEqual({k: v["max"] for k, v in s["sectors"].items()},
                         {"E": 2, "S": 3, "N": 2})

    def test_no_high_risk_on_the_caribbean_shore(self):
        """The physical check: sargassum arrives from the east, so a 3 has no
        business turning up on the north or west coasts."""
        s = S.summarise(self.pts)
        self.assertLess(s["leeward_max"], s["island_max"])
        self.assertEqual(s["sectors"]["N"]["max"], 2)
