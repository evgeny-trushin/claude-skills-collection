import importlib.util
import pathlib
import unittest

SCRIPT_PATH = pathlib.Path(__file__).with_name("05_predict_two_dollars_delivery_order.py")
SPEC = importlib.util.spec_from_file_location("two_dollar_delivery", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ExplainBlockTest(unittest.TestCase):
    def test_direct_block_reason(self):
        reason = MODULE.explain_block(
            "Beerenberg Tomato Sauce 300mL", {"Beerenberg Tomato Sauce 300mL"}, {})
        self.assertIsNotNone(reason)
        self.assertIn("Beerenberg Tomato Sauce 300mL", reason)

    def test_category_block_names_trigger(self):
        generic = {"Tomato Products": ["Ardmona Diced Tomatoes 400g", "Passata 700g"]}
        reason = MODULE.explain_block(
            "Passata 700g", {"Ardmona Diced Tomatoes 400g"}, generic)
        self.assertIsNotNone(reason)
        self.assertIn("Ardmona Diced Tomatoes 400g", reason)
        self.assertIn("Tomato Products", reason)

    def test_unblocked_returns_none(self):
        self.assertIsNone(MODULE.explain_block("Free Item", set(), {}))


if __name__ == "__main__":
    unittest.main()
