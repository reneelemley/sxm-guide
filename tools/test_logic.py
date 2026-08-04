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
        out = build_today.build(dt.date(2030, 2, 14))
        self.assertIn("TRAFFIC_DATA_STALE", out["slots"])
        self.assertFalse(any(s.startswith("TRAFFIC_") and s != "TRAFFIC_DATA_STALE"
                             for s in out["slots"]))
        self.assertIsNone(out["traffic"]["severity"])

    def test_known_date_reports_normally(self):
        import build_today
        out = build_today.build(dt.date(2026, 8, 4))
        self.assertTrue(out["traffic"]["ships_known"])
        self.assertIsNotNone(out["traffic"]["severity"])
