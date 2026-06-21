import importlib.util
import os
import pathlib
import unittest

SCRIPT_PATH = pathlib.Path(__file__).with_name("05_predict_two_dollars_delivery_order.py")
SPEC = importlib.util.spec_from_file_location("two_dollar_delivery", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CategoryBlockingTest(unittest.TestCase):
    def setUp(self):
        os.chdir(pathlib.Path(__file__).parent)
        self.dont_order = MODULE.load_dont_order()
        self.generic = MODULE.load_generic_products()

    def test_wanted_siblings_are_not_blocked(self):
        for wanted in [
            "Coles Organic Unsweetened Oat Milk 1L",
            "Mutti Sugo Pasta Sauce Basil & Onion 400g",
            "Whole Earth Monk Fruit 100% Natural Sweetener 200g",
        ]:
            self.assertFalse(
                MODULE.is_product_blocked(wanted, self.dont_order, self.generic),
                f"{wanted} should NOT be blocked",
            )

    def test_intentional_blocks_still_block(self):
        for blocked in [
            "Coles Unsweetened Oat Milk 1L",
            "Mutti Sugo Semplice Basil & Onion 400g",
            "Whole Earth Sugar Raw Replacement 200g",
            "Ardmona Diced Tomatoes 400g",
        ]:
            self.assertTrue(
                MODULE.is_product_blocked(blocked, self.dont_order, self.generic),
                f"{blocked} should still be blocked",
            )


if __name__ == "__main__":
    unittest.main()
