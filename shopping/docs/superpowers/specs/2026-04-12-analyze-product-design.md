# Analyze Product Group — Design Spec

## Goal

Add `--analyze <group>` CLI flag to `05_predict_two_dollars_delivery_order.py` that produces a focused, end-to-end diagnostic report for a single generic product group (e.g. coffee). The full prediction runs as usual; the analysis is appended afterward. Output is both a colored terminal report and a standalone HTML page.

## CLI Interface

```
python3 05_predict_two_dollars_delivery_order.py --analyze coffee
```

- `argparse` in `__main__`, optional positional-free flag.
- The value is matched **case-insensitively** against keys in `generic-products.json`.
- If no group matches: print available groups and exit with error.
- Without `--analyze`: script behaves exactly as today.

## Data Flow

1. Full prediction pipeline runs unchanged (load → promo → stats → orders → terminal + HTML report).
2. If `--analyze` is set, call new function `analyze_product_group(...)` after the normal run.
3. `analyze_product_group` receives already-computed data: `df_grouped`, `product_stats`, `orders`, `promo_info`, `product_prices`, `generic_mappings`, `in_stock_dict`, `stock_date`, `prediction_start`, `last_invoice_date`.
4. It filters, re-runs consumption metrics to capture anomaly details, and renders the report.

## Change to `calculate_consumption_metrics`

**Current**: anomaly exclusions are `print()`ed and dropped. Returns 7 values.

**New**: return `excluded_rows` as an 8th value — a list of dicts:
```python
{"date": row["ds"], "qty": row["y"], "threshold": upper_bound, "median": median_val}
```

All existing call sites (lines 472, 605) updated to unpack the 8th value (can use `_` where not needed, or store for debug).

## `analyze_product_group` Function

### Inputs

- `group_name`: str — the generic-products.json key
- `df_grouped`: full DataFrame
- `product_stats`: dict from `compute_product_stats`
- `orders`: list of order dicts from `build_minimal_orders` (post-consolidation)
- `promo_info`: dict from `analyze_price_patterns`
- `product_prices`: dict of current prices
- `generic_mappings`: dict from `generic-products.json`
- `in_stock_dict`, `stock_date`: from `load_in_stock`
- `prediction_start`, `last_invoice_date`: dates

### Logic

1. Look up `group_products = generic_mappings[group_name]`.
2. Filter `df_grouped` to rows where `product` is in `group_products`.
3. Aggregate by date (same as `compute_product_stats` group path, line 468).
4. Call `calculate_consumption_metrics` on aggregated data to get metrics + `excluded_rows`.
5. Find the representative product in `product_stats` (the one with `is_group_representative=True` and `group_name` matching).
6. Scan `orders` for items matching the representative.
7. Pull promo info for products in the group.
8. Render terminal report (colored).
9. Write HTML report.

### Terminal Report Sections

```
=== ANALYSIS: Coffee ===
Group products: Vittoria Coffee Beans 1kg, Nescafe Gold Coffee ...
Representative: Vittoria Coffee Beans 1kg ($12.50)

1. RAW ORDER HISTORY
   Date        Product                    Qty   Price
   2025-12-01  Vittoria Coffee Beans 1kg  2     $12.50
   ...

2. ANOMALIES EXCLUDED
   Date        Qty   Threshold  Median   Reason
   2025-11-15  8     5.0        2.0      Upper outlier
   (or: "None detected")

3. CONSUMPTION METRICS
   Daily rate: 0.28 | Avg interval: 14d | Avg qty/order: 2.0
   Order count: 12 | Total qty: 24

4. STOCK ESTIMATE
   Source: actual | Stock date: 2025-12-20 | Current: 1.2 units
   Days until empty: 4.3

5. ORDER PLAN
   Order #1 (2025-12-25): 2x Vittoria Coffee Beans 1kg = $25.00
   Order #3 (2026-01-08): 2x Vittoria Coffee Beans 1kg = $25.00
   (or: "Not scheduled in any order")

6. PROMO PATTERNS
   Has promos: Yes | Min $10.00 -> Max $14.00 | Savings: 28%
   Best days: Tuesday, Friday | Best weeks: 1, 2
```

### HTML Report

- Standalone HTML page: `output_extracted/analyze-<group_name>.html`
- Same inline-CSS approach as existing `two-dollar-delivery-order-plan.html`
- Sections mirror the terminal report above
- Group name slugified for filename (spaces → hyphens, lowercase)

## Shell Wrapper Change

`05_predict_two_dollars_delivery_order.sh` line 36:

```bash
# Before:
python3 05_predict_two_dollars_delivery_order.py
# After:
python3 05_predict_two_dollars_delivery_order.py "$@"
```

## Files Changed

| File | Change |
|------|--------|
| `05_predict_two_dollars_delivery_order.py` | Add `argparse`, modify `calculate_consumption_metrics` return, add `analyze_product_group`, add `write_analyze_html`, update `__main__` |
| `05_predict_two_dollars_delivery_order.sh` | Forward `"$@"` |

## Not In Scope

- Matching by individual product name substring (only generic group keys)
- Removing existing `DEBUG_PRODUCTS` tracing (separate cleanup)
- Changes to the normal prediction pipeline logic
