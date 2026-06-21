import importlib.util
import pathlib
import unittest

import pandas as pd

SCRIPT_PATH = pathlib.Path(__file__).with_name("05_predict_two_dollars_delivery_order.py")
SPEC = importlib.util.spec_from_file_location("two_dollar_delivery", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ProductFamilyTest(unittest.TestCase):
    def test_egg_skus_pool_into_one_family(self):
        df = pd.DataFrame([
            ["Coles Free Range Eggs 12 Pack 700g", pd.Timestamp("2026-05-01"), 1],
            ["Sunny Queen Free Range Large Eggs 18 Pack 900g", pd.Timestamp("2026-05-12"), 1],
        ], columns=["product", "ds", "y"])
        families = {"Eggs": [
            "Coles Free Range Eggs 12 Pack 700g",
            "Sunny Queen Free Range Large Eggs 18 Pack 900g",
        ]}
        out = MODULE.apply_product_families(df, families)
        self.assertIn("Eggs", set(out["product"]))
        self.assertNotIn("Coles Free Range Eggs 12 Pack 700g", set(out["product"]))
        # two purchases 11 days apart now form one cadence series
        self.assertEqual(len(out[out["product"] == "Eggs"]), 2)

    def test_same_day_family_purchases_sum(self):
        df = pd.DataFrame([
            ["Coles Free Range Eggs 12 Pack 700g", pd.Timestamp("2026-05-01"), 1],
            ["Coles Cage Free Eggs 12 Pack 700g", pd.Timestamp("2026-05-01"), 2],
        ], columns=["product", "ds", "y"])
        families = {"Eggs": [
            "Coles Free Range Eggs 12 Pack 700g",
            "Coles Cage Free Eggs 12 Pack 700g",
        ]}
        out = MODULE.apply_product_families(df, families)
        eggs = out[out["product"] == "Eggs"]
        self.assertEqual(len(eggs), 1)
        self.assertEqual(eggs.iloc[0]["y"], 3)

    def test_non_family_products_untouched(self):
        df = pd.DataFrame([
            ["Coles Brown Rice 1 kg", pd.Timestamp("2026-05-01"), 1],
        ], columns=["product", "ds", "y"])
        out = MODULE.apply_product_families(df, {"Eggs": ["Coles Free Range Eggs 12 Pack 700g"]})
        self.assertIn("Coles Brown Rice 1 kg", set(out["product"]))

    def test_empty_families_returns_input(self):
        df = pd.DataFrame([
            ["Anything", pd.Timestamp("2026-05-01"), 1],
        ], columns=["product", "ds", "y"])
        out = MODULE.apply_product_families(df, {})
        self.assertIn("Anything", set(out["product"]))


class FamilyPriceTest(unittest.TestCase):
    def test_family_price_inherits_most_recent_member(self):
        product_prices = {
            "Coles Free Range Eggs 12 Pack 700g": {"price": 5.0, "date": pd.Timestamp("2026-04-01")},
            "Sunny Queen Free Range Large Eggs 18 Pack 900g": {"price": 9.0, "date": pd.Timestamp("2026-05-01")},
        }
        families = {"Eggs": list(product_prices.keys())}
        out = MODULE.merge_family_prices(product_prices, families)
        self.assertIn("Eggs", out)
        self.assertEqual(out["Eggs"]["price"], 9.0)

    def test_family_with_no_priced_members_skipped(self):
        out = MODULE.merge_family_prices({}, {"Eggs": ["Coles Free Range Eggs 12 Pack 700g"]})
        self.assertNotIn("Eggs", out)


if __name__ == "__main__":
    unittest.main()
