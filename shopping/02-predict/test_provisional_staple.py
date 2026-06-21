import importlib.util
import pathlib
import unittest

import pandas as pd

SCRIPT_PATH = pathlib.Path(__file__).with_name("05_predict_two_dollars_delivery_order.py")
SPEC = importlib.util.spec_from_file_location("two_dollar_delivery", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ProvisionalStapleTest(unittest.TestCase):
    def test_rapid_new_item_is_staple(self):
        dates = [pd.Timestamp(d) for d in ["2026-05-01", "2026-05-11", "2026-05-21"]]
        self.assertTrue(MODULE.is_provisional_staple(dates, pd.Timestamp("2026-05-25")))

    def test_sparse_item_is_not(self):
        dates = [pd.Timestamp(d) for d in ["2026-01-01", "2026-03-01"]]
        self.assertFalse(MODULE.is_provisional_staple(dates, pd.Timestamp("2026-05-25")))

    def test_old_recurrences_outside_window_not_staple(self):
        dates = [pd.Timestamp(d) for d in ["2026-01-01", "2026-01-11", "2026-01-21"]]
        self.assertFalse(MODULE.is_provisional_staple(dates, pd.Timestamp("2026-05-25")))

    def test_none_dates_safe(self):
        self.assertFalse(MODULE.is_provisional_staple(None, pd.Timestamp("2026-05-25")))


if __name__ == "__main__":
    unittest.main()
