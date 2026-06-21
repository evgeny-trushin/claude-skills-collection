import importlib.util
import pathlib
import unittest

import pandas as pd

SCRIPT_PATH = pathlib.Path(__file__).with_name("05_predict_two_dollars_delivery_order.py")
SPEC = importlib.util.spec_from_file_location("two_dollar_delivery", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RecencyRateTest(unittest.TestCase):
    def test_ramping_weighted_higher_than_declining(self):
        # Same quantities {1,2,3,4} at a steady 10-day cadence, opposite order.
        # Recency weighting must rate the rising series higher than the falling one.
        dates = [pd.Timestamp(d) for d in
                 ["2026-04-01", "2026-04-11", "2026-04-21", "2026-05-01"]]
        ramping = MODULE.recency_weighted_daily_rate(dates, [1, 2, 3, 4])
        declining = MODULE.recency_weighted_daily_rate(dates, [4, 3, 2, 1])
        self.assertGreater(ramping, declining)
        # and the rising series must beat the flat all-orders-equal mean (2.5/10)
        self.assertGreater(ramping, 2.5 / 10)

    def test_steady_consumption_matches_flat_rate(self):
        # steady 1 unit / 10 days -> 0.1/day regardless of weighting
        dates = [pd.Timestamp(d) for d in
                 ["2026-04-01", "2026-04-11", "2026-04-21", "2026-05-01"]]
        qtys = [1, 1, 1, 1]
        weighted = MODULE.recency_weighted_daily_rate(dates, qtys)
        self.assertAlmostEqual(weighted, 0.1, places=3)

    def test_single_order_returns_zero(self):
        self.assertEqual(
            MODULE.recency_weighted_daily_rate([pd.Timestamp("2026-05-01")], [1]), 0.0)


if __name__ == "__main__":
    unittest.main()
