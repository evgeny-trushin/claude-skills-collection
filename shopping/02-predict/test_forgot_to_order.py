import importlib.util
import pathlib
import unittest

import pandas as pd

SCRIPT_PATH = pathlib.Path(__file__).with_name("05_predict_two_dollars_delivery_order.py")
SPEC = importlib.util.spec_from_file_location("two_dollar_delivery", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _df(rows):
    return pd.DataFrame(rows, columns=["product", "ds", "y"])


class ForgotToOrderTest(unittest.TestCase):
    def test_overdue_staple_is_flagged(self):
        # Eggs every ~11 days, last bought 50 days before reference -> overdue
        rows = [["Eggs", pd.Timestamp(day), 1] for day in
                ["2026-02-01", "2026-02-12", "2026-02-23",
                 "2026-03-06", "2026-03-17", "2026-03-28"]]
        result = MODULE.find_forgotten_staples(
            _df(rows), pd.Timestamp("2026-05-17"), set(), {})
        self.assertIn("Eggs", [r["product"] for r in result])

    def test_on_cadence_staple_not_flagged(self):
        rows = [["Milk", pd.Timestamp(day), 1] for day in
                ["2026-05-01", "2026-05-08", "2026-05-15"]]
        result = MODULE.find_forgotten_staples(
            _df(rows), pd.Timestamp("2026-05-20"), set(), {})  # 5 days, < 7d cadence
        self.assertNotIn("Milk", [r["product"] for r in result])

    def test_blocked_staple_suppressed(self):
        rows = [["Soda", pd.Timestamp(d), 1] for d in
                ["2026-02-01", "2026-02-12", "2026-02-23", "2026-03-06"]]
        result = MODULE.find_forgotten_staples(
            _df(rows), pd.Timestamp("2026-05-17"), {"Soda"}, {})
        self.assertNotIn("Soda", [r["product"] for r in result])

    def test_too_few_purchases_ignored(self):
        rows = [["Rare", pd.Timestamp(d), 1] for d in ["2026-01-01", "2026-02-01"]]
        result = MODULE.find_forgotten_staples(
            _df(rows), pd.Timestamp("2026-06-01"), set(), {})
        self.assertNotIn("Rare", [r["product"] for r in result])

    def test_zero_price_junk_excluded_when_prices_given(self):
        # Flyers/magazines have no real price -> not orderable groceries
        rows = [["CFC Flyer B 1 Each", pd.Timestamp(d), 1] for d in
                ["2026-02-01", "2026-02-04", "2026-02-07", "2026-02-10"]]
        result = MODULE.find_forgotten_staples(
            _df(rows), pd.Timestamp("2026-06-01"), set(), {}, product_prices={})
        self.assertNotIn("CFC Flyer B 1 Each", [r["product"] for r in result])

    def test_priced_staple_kept_when_prices_given(self):
        rows = [["Eggs", pd.Timestamp(d), 1] for d in
                ["2026-02-01", "2026-02-12", "2026-02-23", "2026-03-06"]]
        result = MODULE.find_forgotten_staples(
            _df(rows), pd.Timestamp("2026-05-17"), set(), {},
            product_prices={"Eggs": {"price": 6.0}})
        self.assertIn("Eggs", [r["product"] for r in result])


if __name__ == "__main__":
    unittest.main()
