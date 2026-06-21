import importlib.util
import pathlib
import unittest
from datetime import datetime


SCRIPT_PATH = pathlib.Path(__file__).with_name("05_predict_two_dollars_delivery_order.py")
SPEC = importlib.util.spec_from_file_location("two_dollar_delivery", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CombinedPromptTest(unittest.TestCase):
    def test_combined_prompt_contains_all_active_order_items_once(self):
        orders = [
            {
                "date": datetime(2026, 5, 9),
                "items": [
                    {"product": "Coles Bread", "qty": 1, "total_price": 4.0},
                    {"product": "%Coles Milk", "qty": 2, "total_price": 9.0},
                ],
            },
            {
                "date": datetime(2026, 5, 12),
                "items": [
                    {"product": "Coles Eggs", "qty": 12, "total_price": 6.5},
                ],
            },
            {
                "date": datetime(2026, 5, 16),
                "items": [
                    {"product": "Skipped Product", "qty": 1, "total_price": 10.0},
                ],
                "skipped": True,
            },
        ]

        prompt = MODULE._build_combined_reorder_prompt(orders)

        self.assertEqual(prompt.count("Reorder via https://www.coles.com.au"), 1)
        self.assertIn("these items:", prompt)
        self.assertNotIn("ORDER DATE:", prompt)
        self.assertNotIn("Saturday, 09 May 2026", prompt)
        self.assertIn("Coles Milk x2", prompt)
        self.assertIn("Coles Bread x1", prompt)
        self.assertNotIn("Tuesday, 12 May 2026", prompt)
        self.assertIn("Coles Eggs x12", prompt)
        self.assertNotIn("Skipped Product", prompt)


if __name__ == "__main__":
    unittest.main()
