import importlib.util
import pathlib
import unittest

import pandas as pd

SCRIPT_PATH = pathlib.Path(__file__).with_name("05_predict_two_dollars_delivery_order.py")
SPEC = importlib.util.spec_from_file_location("two_dollar_delivery", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _invoice(date, items):
    return {
        "invoice_date": date,
        "categories": [{"items": [{"product": p, "ordered": q} for p, q in items]}],
    }


class FutureInvoiceGuardTest(unittest.TestCase):
    def test_future_invoice_detected(self):
        self.assertTrue(MODULE.is_future_invoice(
            pd.Timestamp("2027-01-17"), pd.Timestamp("2026-06-21")))

    def test_past_invoice_ok(self):
        self.assertFalse(MODULE.is_future_invoice(
            pd.Timestamp("2026-06-20"), pd.Timestamp("2026-06-21")))

    def test_today_is_ok(self):
        self.assertFalse(MODULE.is_future_invoice(
            pd.Timestamp("2026-06-21"), pd.Timestamp("2026-06-21")))


class DedupeInvoicesTest(unittest.TestCase):
    def test_exact_duplicate_removed(self):
        a = _invoice("06 February 2026", [("Eggs", 1), ("Milk", 2)])
        b = _invoice("06 February 2026", [("Eggs", 1), ("Milk", 2)])
        out = MODULE.dedupe_invoices([a, b])
        self.assertEqual(len(out), 1)

    def test_same_day_different_items_kept(self):
        a = _invoice("06 February 2026", [("Eggs", 1)])
        b = _invoice("06 February 2026", [("Bread", 1)])
        out = MODULE.dedupe_invoices([a, b])
        self.assertEqual(len(out), 2)

    def test_distinct_dates_kept(self):
        a = _invoice("06 February 2026", [("Eggs", 1)])
        b = _invoice("07 February 2026", [("Eggs", 1)])
        out = MODULE.dedupe_invoices([a, b])
        self.assertEqual(len(out), 2)


if __name__ == "__main__":
    unittest.main()
