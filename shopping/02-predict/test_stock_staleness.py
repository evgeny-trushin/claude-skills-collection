import importlib.util
import pathlib
import unittest

import pandas as pd

SCRIPT_PATH = pathlib.Path(__file__).with_name("05_predict_two_dollars_delivery_order.py")
SPEC = importlib.util.spec_from_file_location("two_dollar_delivery", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class StockStalenessTest(unittest.TestCase):
    def test_old_snapshot_is_stale(self):
        self.assertTrue(MODULE.is_stock_stale(
            pd.Timestamp("2026-01-21"), pd.Timestamp("2026-06-21")))

    def test_recent_snapshot_is_fresh(self):
        self.assertFalse(MODULE.is_stock_stale(
            pd.Timestamp("2026-06-10"), pd.Timestamp("2026-06-21")))

    def test_missing_date_is_not_stale(self):
        self.assertFalse(MODULE.is_stock_stale(None, pd.Timestamp("2026-06-21")))

    def test_boundary_uses_threshold(self):
        self.assertFalse(MODULE.is_stock_stale(
            pd.Timestamp("2026-06-01"), pd.Timestamp("2026-06-21"), max_age_days=30))
        self.assertTrue(MODULE.is_stock_stale(
            pd.Timestamp("2026-05-01"), pd.Timestamp("2026-06-21"), max_age_days=30))


if __name__ == "__main__":
    unittest.main()
