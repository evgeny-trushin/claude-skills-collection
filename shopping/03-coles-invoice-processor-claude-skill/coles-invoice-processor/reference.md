# Coles Invoice Processor Reference

## Script Reference

### 01_convert.py - PDF to Markdown Converter

Converts PDF invoices to Markdown format using `pymupdf4llm`.

**Input:** `input_invoices/*.pdf`
**Output:** `input_invoices/*.md` (same directory)

```python
# Key function
def convert_pdfs_to_markdown():
    # Finds all PDFs in INPUT_DIR
    # Converts each to Markdown using pymupdf4llm.to_markdown()
    # Saves with same filename but .md extension
```

### 03_extract_data.py - Data Extractor

Parses Markdown invoices and extracts structured data.

**Input:** `input_invoices/*.md`
**Output:** `output_extracted/extracted_data.json`

```python
# Key patterns
inv_num_match = re.search(r'\*\*Invoice number:\*\* #?(\[REDACTED\]|\d+)?', content)
date_match = re.search(r'\*\*Invoice date:\*\* (\d+ \w+ \d{4})', content)
time_match = re.search(r'\*\*Invoice time:\*\* (\d+:\d+:\d+)', content)

# Weight extraction regex
weight_match = re.search(r'(?i)((?:approx\.?\s*)?\d+(?:\.\d+)?\s*(?:g|kg|ml|l|litre|liter|m|metre|meter|pack|each|pk))\s*$', name)
```

### 04_predict_orders.py - Order Predictor

Forecasts future orders based on purchase history.

**Input:** `output_extracted/extracted_data.json`
**Output:** Console output with predicted orders and monthly budget

**Configuration:**
```python
FORECAST_DAYS = 150  # ~5 months forecast horizon
MIN_ORDER = 50       # Minimum order value before merging
```

**Algorithm:**
1. Load extracted data
2. Build product purchase history
3. Calculate average interval between purchases
4. Calculate average quantity per purchase
5. Project future orders starting from today
6. Group orders within 3 days
7. Merge orders under $50 with adjacent orders within 6 days

## Invoice Format Examples

### Markdown Format (from PDF conversion)
```markdown
**Invoice number:** #123456
**Invoice date:** 7 December 2024
**Invoice time:** 14:30:00

**Dairy**

**Product** **Ordered** **Picked** **Unit Price** **Total charged**

[Coles Full Cream Milk 2L](https://...) 2 2 $3.50 $7.00
[Babushka's Probiotic Kefir Yoghurt 500g](https://...) 1 1 $6.50 $6.50
```

### Raw Text Format
```
Invoice number: #123456
Invoice date: 7 December 2024

Dairy
Product          Ordered  Picked  Unit Price  Total
Coles Full Cream Milk 2L    2       2      $3.50    $7.00
```

## Data Extraction Patterns

### Invoice Number
- Pattern: `\*\*Invoice number:\*\* #?(\[REDACTED\]|\d+)?`
- Example: `**Invoice number:** #123456` → `123456`

### Invoice Date
- Pattern: `\*\*Invoice date:\*\* (\d+ \w+ \d{4})`
- Example: `**Invoice date:** 7 December 2024` → `7 December 2024`
- Parse as: day month year format

### Invoice Time
- Pattern: `\*\*Invoice time:\*\* (\d+:\d+:\d+)`
- Example: `**Invoice time:** 14:30:00` → `14:30:00`

### Category Detection
- Look for header: `**Product** **Ordered** **Picked** **Unit Price** **Total charged**`
- Category name is the preceding `**Bold**` line

### Product Lines
- Markdown: `[Product Name](url) Ordered Picked $UnitPrice $TotalPrice`
- Stats may be on next line if line wraps

### Weight/Size Extraction
Common patterns in product names:
- Volume: `2L`, `3L`, `500mL`, `1 Litre`
- Weight: `500g`, `1kg`, `200g`
- Count: `12 Pack`, `6pk`, `4 Pack`
- Each: `1 EACH`, `each`

Regex: `(?i)((?:approx\.?\s*)?\d+(?:\.\d+)?\s*(?:g|kg|ml|l|litre|liter|m|metre|meter|pack|each|pk))\s*$`

## Prediction Algorithm

### Step 1: Build Purchase History
For each product across all invoices:
```python
rows.append({
    'ds': date,        # Purchase date
    'product': product,
    'y': quantity      # Quantity purchased
})
```

### Step 2: Calculate Intervals
```python
product_df['interval'] = product_df['ds'].diff().dt.days
avg_interval = product_df['interval'].mean()
interval_days = round(avg_interval)
```

### Step 3: Calculate Average Quantity
```python
avg_qty = product_df['y'].mean()
rounded_qty = max(1, round(avg_qty))
```

### Step 4: Project Future Orders
```python
# Start from last purchase + interval
next_order_date = last_date + timedelta(days=interval_days)

# Skip past dates
while next_order_date < today:
    next_order_date = next_order_date + timedelta(days=interval_days)

# Generate orders until forecast horizon
while next_order_date <= forecast_end:
    predictions.append({...})
    next_order_date = next_order_date + timedelta(days=interval_days)
```

### Step 5: Group Orders (within 3 days)
```python
if (p['next_order_date'] - group_start_date).days <= 3:
    current_group.append(p)
else:
    bulk_orders.append(current_group)
    current_group = [p]
```

### Step 6: Merge Small Orders (<$50)
```python
MIN_ORDER = 50
if current_total < MIN_ORDER and i + 1 < len(bulk_orders):
    next_date = next_order[0]['next_order_date']
    if (next_date - current_date).days <= 6:
        # Merge with next order
```

## Output JSON Schema

### Extracted Data (extracted_data.json)
```json
[
  {
    "filename": "ea[REDACTED]_044712.md",
    "invoice_number": "[REDACTED]",
    "invoice_date": "7 December 2024",
    "invoice_time": "14:30:00",
    "categories": [
      {
        "name": "Dairy",
        "items": [
          {
            "product": "Coles Full Cream Milk 3L",
            "weight": "3L",
            "link": "https://...",
            "ordered": "2",
            "picked": "2",
            "unit_price": "$4.65",
            "total_price": "$9.30"
          }
        ]
      }
    ]
  }
]
```

### Prediction Output Structure
```python
predictions = [{
    'product': str,
    'next_order_date': datetime,
    'predicted_qty': int,
    'unit_price': float,
    'total_price': float,
    'interval': int
}]

monthly_budget = {
    'YYYY-Month': float  # e.g., '2025-December': 785.80
}
```

## Common Coles Product Categories

| Category | Examples |
|----------|----------|
| Dairy | Milk, Yoghurt, Cheese, Butter |
| Bakery | Bread, Rolls, Pastries |
| Meat & Seafood | Chicken, Beef, Fish, Mince |
| Fruit & Vegetables | Apples, Bananas, Broccoli, Potatoes |
| Pantry | Pasta, Rice, Sauces, Canned goods |
| Frozen | Pizza, Ice cream, Frozen vegetables |
| Drinks | Juice, Soft drinks, Water |
| Health & Beauty | Toiletries, Vitamins, Personal care |
| Baby | Wipes, Formula, Baby food |
| Household | Cleaning, Laundry, Paper products |

## Price Parsing

```python
price_str = item.get('unit_price', '0').replace('$', '').replace(',', '')
price = float(price_str)
```

## Handling Edge Cases

### Missing Data
- If picked ≠ ordered: Note substitutions or unavailable items
- If no price: Skip item or use $0.00
- If no date: Cannot include in predictions
- Products with <2 purchases: Skip prediction

### Multi-page Invoices
- Same category may appear on multiple pages
- Script merges items into existing category

### Substituted Items
- Original item shows ordered > picked
- Substituted item may appear separately

### Filename Redaction
```python
# ea12345_67890.md -> ea[REDACTED]_67890.md
filename_match = re.match(r'(ea)\d+(_\d+\.md)', md_file, re.IGNORECASE)
if filename_match:
    redacted_filename = filename_match.group(1) + "[REDACTED]" + filename_match.group(2)
```
