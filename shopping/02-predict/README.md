Shopping Invoice Pipeline

- `pdf2markdown.sh`: sets up `.venv`, installs `requirements.txt`, then runs `01_convert.py`, `02_obfuscate.py`, and `03_extract_data.py` in sequence.
- `01_convert.py`: converts each PDF in `input_invoices/` to a Markdown file in the same folder using `pymupdf4llm`.
- `02_obfuscate.py`: replaces sensitive strings in the Markdown files using `obfuscate.online.json` and redacts invoice numbers.
- `03_extract_data.py`: parses the Markdown invoices, builds structured categories/items, and writes `output_extracted/extracted_data.json` (creates the folder if missing).
- `predict-orders.sh`: sets up `.venv`, installs dependencies (Prophet), and runs `04_predict_orders.py`.
- `04_predict_orders.py`: loads `extracted_data.json`, infers purchase intervals and quantities per product, forecasts ~150 days ahead, groups nearby orders, and prints suggested bulk orders plus a monthly budget.
- `05_predict_two_dollars_delivery_order.sh`: sets up `.venv`, installs dependencies, and runs `05_predict_two_dollars_delivery_order.py` for a $2 delivery plan.
- `05_predict_two_dollars_delivery_order.py`: calculates weekly consumption per product, plans 3 orders per week that respect a $50 minimum, caps storage at 2 units per product (frequent items up to 5), and includes a $2 delivery fee in the spend view.

Usage
- Place invoice PDFs in `input_invoices/`, run `./pdf2markdown.sh`, then run `./predict-orders.sh` to see forecasted orders.
- Run `./05_predict_two_dollars_delivery_order.sh` to view the $2 delivery optimized plan.
