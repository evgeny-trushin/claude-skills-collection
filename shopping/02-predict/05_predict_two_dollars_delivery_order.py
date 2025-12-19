import json
import logging
import os
import math
from datetime import timedelta

import pandas as pd

# Suppress noisy logs from Prophet dependency if it is installed
logging.getLogger("cmdstanpy").setLevel(logging.ERROR)
logging.getLogger("prophet").setLevel(logging.ERROR)

OUTPUT_DIR = "output_extracted"
MIN_ORDER_TOTAL = 50  # Coles minimum order requirement
DELIVERY_FEE = 2.0    # assumed flat delivery fee per order
ORDERS_PER_WEEK = 2   # optimal for catching discounts
# Based on analysis: Tuesday (60% discount rate) and Saturday (44% discount rate)
ORDER_DAYS = ["Tuesday", "Saturday"]  # best days for Coles discounts
ORDER_OFFSETS = [1, 5]  # Tuesday=1, Saturday=5 (Monday=0)
PREDICTION_WINDOW_DAYS = 30  # only plan one month ahead from last invoice

# Promotional pattern insights from historical data
BEST_DISCOUNT_DAYS = ["Tuesday", "Friday", "Saturday"]
BEST_DISCOUNT_WEEKS = [1, 2, 5]  # Week of month (1=days 1-7, 5=days 29-31)
WORST_DISCOUNT_WEEK = 4  # Days 22-28 - avoid if possible


def load_in_stock():
    """Load in-stock data from in-stock.json and return a dict with fuzzy-matched product names."""
    stock_file = os.path.join(OUTPUT_DIR, "in-stock.json")
    if not os.path.exists(stock_file):
        print(f"Note: {stock_file} not found. Using estimated stock levels.")
        return {}, None

    try:
        with open(stock_file, "r") as f:
            stock_data = json.load(f)

        stock_date = stock_data.get("stock_date")
        if stock_date:
            stock_date = pd.to_datetime(stock_date)

        # Create a mapping of partial names to quantities
        in_stock = {}
        for item in stock_data.get("items", []):
            product_partial = item.get("product", "").lower().strip()
            quantity = item.get("quantity", 0)
            in_stock[product_partial] = quantity

        print(f"Loaded in-stock data from {stock_date.strftime('%Y-%m-%d') if stock_date else 'unknown date'}: {len(in_stock)} items")
        return in_stock, stock_date
    except Exception as e:
        print(f"Warning: Error loading in-stock.json: {e}")
        return {}, None


def match_product_to_stock(product_name, in_stock_dict):
    """Fuzzy match a product name to items in the in-stock dictionary."""
    # Normalize the product name: remove %, strip, lowercase
    product_lower = product_name.lower().replace("%", "").strip()
    # Remove possessives and normalize apostrophes
    product_lower = product_lower.replace("''s", "").replace("'s", "").replace("'s", "")
    product_lower = product_lower.replace("''", " ").replace("'", " ").replace("'", " ")
    # Normalize multiple spaces
    product_lower = " ".join(product_lower.split())

    # Direct match check - check if all words from stock key appear in product
    for stock_key, qty in in_stock_dict.items():
        # Also normalize stock key
        stock_normalized = stock_key.replace("''s", "").replace("'s", "").replace("'s", "")
        stock_normalized = stock_normalized.replace("''", " ").replace("'", " ").replace("'", " ")
        stock_normalized = " ".join(stock_normalized.split())

        # Check if stock key words are in product (allows for extra words in product)
        stock_words = stock_normalized.split()
        product_words = product_lower.split()

        if all(word in product_words for word in stock_words):
            return qty

    return None


def load_grouped_orders():
    data_file = os.path.join(OUTPUT_DIR, "extracted_data.json")
    if not os.path.exists(data_file):
        print(f"Error: {data_file} not found. Please run extraction first.")
        return None, {}, None, {}

    with open(data_file, "r") as f:
        data = json.load(f)

    rows = []
    product_prices = {}  # Most recent price per product
    price_history = {}   # Full price history: {product: [(date, price, qty), ...]}
    last_invoice_date = None

    for invoice in data:
        date_str = invoice.get("invoice_date")
        if not date_str:
            continue

        try:
            date = pd.to_datetime(date_str, format="%d %B %Y")
        except Exception:
            try:
                date = pd.to_datetime(date_str)
            except Exception:
                continue

        # Track the most recent invoice date
        if last_invoice_date is None or date > last_invoice_date:
            last_invoice_date = date

        for category in invoice.get("categories", []):
            for item in category.get("items", []):
                product = item.get("product")
                try:
                    quantity = float(item.get("ordered", 0))
                except ValueError:
                    quantity = 0

                try:
                    price_str = str(item.get("unit_price", "0")).replace("$", "").replace(",", "")
                    price = float(price_str)
                    if price > 0:
                        # Track price history
                        if product not in price_history:
                            price_history[product] = []
                        price_history[product].append({
                            "date": date,
                            "price": price,
                            "qty": quantity
                        })

                        # Track most recent price
                        if product and (product not in product_prices or date > product_prices[product]["date"]):
                            product_prices[product] = {"price": price, "date": date}
                except Exception:
                    pass

                if product and quantity > 0:
                    rows.append({"ds": date, "product": product, "y": quantity})

    df = pd.DataFrame(rows)
    if df.empty:
        return None, product_prices, last_invoice_date, price_history

    df_grouped = df.groupby(["product", "ds"]).sum().reset_index()
    return df_grouped, product_prices, last_invoice_date, price_history


def analyze_price_patterns(price_history):
    """Analyze price history to detect promotions and bulk-buy patterns."""
    promo_info = {}

    for product, history in price_history.items():
        if len(history) < 2:
            continue

        # Sort by date
        history = sorted(history, key=lambda x: x["date"])
        prices = [h["price"] for h in history]
        quantities = [h["qty"] for h in history]

        min_price = min(prices)
        max_price = max(prices)
        avg_price = sum(prices) / len(prices)
        current_price = history[-1]["price"]

        # Calculate price variance
        price_range = max_price - min_price
        price_variance_pct = (price_range / avg_price * 100) if avg_price > 0 else 0

        # Detect if product has promotional patterns (>10% price variance)
        has_promos = price_variance_pct > 10

        # Find which days had the best (lowest) prices
        best_days = []
        best_weeks = []
        for h in history:
            if h["price"] == min_price:
                day_name = h["date"].day_name()
                week_of_month = (h["date"].day - 1) // 7 + 1
                best_days.append(day_name)
                best_weeks.append(week_of_month)

        # Check if larger quantities were ordered at lower prices
        bulk_at_discount = False
        avg_qty_at_min = 0
        avg_qty_at_max = 0

        for h in history:
            if h["price"] == min_price:
                avg_qty_at_min += h["qty"]
            if h["price"] == max_price:
                avg_qty_at_max += h["qty"]

        min_count = sum(1 for h in history if h["price"] == min_price)
        max_count = sum(1 for h in history if h["price"] == max_price)

        if min_count > 0:
            avg_qty_at_min /= min_count
        if max_count > 0:
            avg_qty_at_max /= max_count

        # If more was ordered at lower prices, likely promotional bulk buy
        if avg_qty_at_min > avg_qty_at_max * 1.5:
            bulk_at_discount = True

        # Calculate potential savings
        savings_per_unit = current_price - min_price
        savings_pct = (savings_per_unit / current_price * 100) if current_price > 0 else 0

        # Determine recommended stock-up quantity when on sale
        # Based on typical order quantity and consumption pattern
        avg_qty = sum(quantities) / len(quantities)
        max_qty_ordered = max(quantities)

        # If item goes on sale, recommend ordering more (up to 2x normal or max ever ordered)
        promo_stock_up = min(max(int(avg_qty * 2), max_qty_ordered), 6)

        promo_info[product] = {
            "has_promos": has_promos,
            "min_price": min_price,
            "max_price": max_price,
            "avg_price": avg_price,
            "current_price": current_price,
            "price_variance_pct": price_variance_pct,
            "bulk_at_discount": bulk_at_discount,
            "savings_per_unit": savings_per_unit,
            "savings_pct": savings_pct,
            "promo_stock_up": promo_stock_up,
            "avg_qty": avg_qty,
            "price_count": len(history),
            "best_days": list(set(best_days)),
            "best_weeks": list(set(best_weeks)),
        }

    return promo_info


def compute_product_stats(df_grouped, product_prices, last_invoice_date, prediction_start, promo_info=None, in_stock_dict=None, stock_date=None):
    """Calculate daily consumption and estimate current stock levels.

    CONSUMPTION CALCULATION LOGIC:
    ================================
    - Consumption window = period between ordering two consecutive same products
    - If ordered only once = time between the oldest invoice and that order
    - Average consumption = total quantity / total time period from oldest invoice to last order

    For stock estimation:
    - If in-stock data provided: use actual stock from in-stock.json
    - Otherwise: last_order_qty - (daily_rate × days_since_last_order)
    """
    stats = {}
    promo_info = promo_info or {}
    in_stock_dict = in_stock_dict or {}

    # Find the oldest invoice date across all products
    oldest_invoice_date = df_grouped["ds"].min()

    for product in df_grouped["product"].unique():
        product_df = df_grouped[df_grouped["product"] == product].sort_values("ds")
        total_qty = product_df["y"].sum()
        if total_qty <= 0:
            continue

        # Skip free/promotional items
        unit_price = product_prices.get(product, {}).get("price", 0.0)
        if unit_price == 0:
            continue

        first_date = product_df["ds"].min()
        last_date = product_df["ds"].max()
        order_count = len(product_df)

        # Calculate order frequency - how often this product appears in orders
        product_df = product_df.copy()
        product_df["interval"] = product_df["ds"].diff().dt.days
        avg_interval = product_df["interval"].mean()

        # Only consider items ordered at least twice, or ordered recently (within last 30 days)
        days_since_last_order = (prediction_start - last_date).days
        if order_count < 2 and days_since_last_order > 30:
            continue  # Skip one-time purchases that are old

        # =========================================================
        # CONSUMPTION RATE CALCULATION
        # =========================================================
        # Consumption period is from the oldest invoice to the last order of this product
        # This gives us the total time period over which consumption occurred

        avg_qty_per_order = total_qty / order_count

        if order_count >= 2:
            # Multiple orders: calculate from first order to last order of this product
            total_consumption_period = (last_date - first_date).days
            if total_consumption_period > 0:
                daily_rate = total_qty / total_consumption_period
            else:
                # Orders on same day - use avg interval from differences
                if avg_interval and not pd.isna(avg_interval) and avg_interval > 0:
                    daily_rate = avg_qty_per_order / avg_interval
                else:
                    daily_rate = avg_qty_per_order / 7  # Default to weekly
        else:
            # Single order: consumption period is from oldest invoice to this order
            total_consumption_period = (last_date - oldest_invoice_date).days
            if total_consumption_period > 0:
                daily_rate = total_qty / total_consumption_period
            else:
                # Order is on the oldest invoice date - default to weekly consumption
                daily_rate = total_qty / 7

        weekly_need = daily_rate * 7

        # Determine if this is a frequently ordered item
        frequent = False
        if order_count >= 3 and avg_interval is not None and not pd.isna(avg_interval) and avg_interval <= 14:
            frequent = True
        elif weekly_need >= 0.5:  # Need at least half unit per week
            frequent = True

        # Calculate max_per_order based on actual ordering behavior
        # Use the average quantity per order as the baseline, rounded up
        max_per_order = max(1, math.ceil(avg_qty_per_order))

        # Get promo info for this product
        pinfo = promo_info.get(product, {})
        has_promos = pinfo.get("has_promos", False)
        promo_stock_up = pinfo.get("promo_stock_up", max_per_order)

        # If product has price promotions, increase max_per_order to allow bulk buying on sale
        if has_promos:
            max_per_order = max(max_per_order, promo_stock_up)

        # Get the last order quantity for this product
        last_order_qty = product_df[product_df["ds"] == last_date]["y"].sum() if not product_df.empty else 0

        # =========================================================
        # STOCK ESTIMATION
        # =========================================================
        # Priority 1: Use actual stock from in-stock.json if available
        # Priority 2: Estimate based on last order depletion model

        actual_stock = match_product_to_stock(product, in_stock_dict)
        stock_source = "estimated"

        if actual_stock is not None and stock_date:
            # Use actual stock from in-stock.json
            # Calculate consumption from stock_date to prediction_start
            days_since_stock_date = (prediction_start - stock_date).days
            consumed_since_stock_date = daily_rate * days_since_stock_date
            estimated_stock = max(0, actual_stock - consumed_since_stock_date)
            stock_source = "actual"
        else:
            # Estimate based on last order depletion model
            consumed_since_last = daily_rate * days_since_last_order
            estimated_stock = max(0, last_order_qty - consumed_since_last)

        # Days until stock runs out
        days_until_empty = estimated_stock / daily_rate if daily_rate > 0 else float('inf')

        stats[product] = {
            "daily_rate": daily_rate,
            "weekly_need": weekly_need,
            "avg_interval": avg_interval,
            "avg_qty_per_order": avg_qty_per_order,
            "frequent": frequent,
            "max_per_order": max_per_order,
            "unit_price": unit_price,
            "estimated_stock": estimated_stock,
            "days_until_empty": days_until_empty,
            "order_count": order_count,
            "last_order_date": last_date,
            "last_order_qty": last_order_qty,
            "days_since_last_order": days_since_last_order,
            "stock_source": stock_source,  # "actual" or "estimated"
            # Promo info
            "has_promos": has_promos,
            "min_price": pinfo.get("min_price", unit_price),
            "max_price": pinfo.get("max_price", unit_price),
            "avg_price": pinfo.get("avg_price", unit_price),
            "price_variance_pct": pinfo.get("price_variance_pct", 0),
            "promo_stock_up": promo_stock_up,
            "savings_pct": pinfo.get("savings_pct", 0),
            "best_days": pinfo.get("best_days", []),
            "best_weeks": pinfo.get("best_weeks", []),
        }
    return stats


def generate_order_dates(start_date, end_date):
    """Generate future order dates several times per week within the planning window."""
    if start_date > end_date:
        return []

    dates = []
    week_start = start_date - timedelta(days=start_date.weekday())  # Monday of this week
    weeks_seen = 0

    while True:
        start = week_start + timedelta(days=7 * weeks_seen)
        if start > end_date:
            break
        for offset in ORDER_OFFSETS[:ORDERS_PER_WEEK]:
            order_date = start + timedelta(days=offset)
            if order_date < start_date or order_date > end_date:
                continue
            dates.append(order_date)
        weeks_seen += 1

    return dates


def build_minimal_orders(product_stats, order_dates, start_date):
    """Build orders that minimize stock by ordering just-in-time based on predicted depletion."""
    orders = [{"date": d, "items": [], "notes": []} for d in order_dates]

    # Sort products by urgency (days until empty)
    sorted_products = sorted(
        product_stats.items(),
        key=lambda x: (x[1]["days_until_empty"], -x[1]["weekly_need"])
    )

    # For each product, calculate when it will run out and schedule orders accordingly
    for product, stats in sorted_products:
        daily_rate = stats["daily_rate"]
        if daily_rate <= 0:
            continue

        # Skip items with very low consumption (less than 1 unit per month)
        if stats["weekly_need"] < 0.25:
            continue

        unit_price = stats["unit_price"]
        max_per_order = stats["max_per_order"]
        estimated_stock = stats["estimated_stock"]

        # Track stock level as we go through order dates
        current_stock = estimated_stock
        last_order_date = start_date

        for order_idx, order in enumerate(orders):
            order_date = order["date"]
            days_elapsed = (order_date - last_order_date).days

            # Consume stock based on days elapsed
            current_stock -= daily_rate * days_elapsed
            last_order_date = order_date

            # Calculate days until next order (or end of planning period)
            if order_idx < len(orders) - 1:
                days_until_next = (orders[order_idx + 1]["date"] - order_date).days
            else:
                days_until_next = 3  # Default buffer for last order

            # How much do we need to last until next order?
            needed_for_period = daily_rate * days_until_next

            # Only order if stock will run out before next order
            if current_stock < needed_for_period:
                shortfall = needed_for_period - current_stock
                # Order in the typical batch size based on historical ordering behavior
                # This respects the user's actual ordering patterns (e.g., buying 3 pizzas at once)
                # Use avg_qty_per_order as the default, but ensure at least the shortfall is covered
                avg_qty = stats["avg_qty_per_order"]
                if shortfall > avg_qty:
                    # Need more than typical order, use max_per_order
                    qty_to_order = max_per_order
                else:
                    # Order the typical amount (rounded to whole units)
                    qty_to_order = max(1, round(avg_qty))

                # Cap at max_per_order
                qty_to_order = min(max_per_order, qty_to_order)

                order["items"].append({
                    "product": product,
                    "qty": qty_to_order,
                    "unit_price": unit_price,
                    "total_price": qty_to_order * unit_price,
                    "max_per_order": max_per_order,
                    "stock_before": round(max(0, current_stock), 1),
                    "need_until_next": round(needed_for_period, 1),
                })
                current_stock += qty_to_order

    return orders


def enforce_minimums(orders, product_stats):
    """Top up orders to reach the $50 minimum when possible within per-product caps."""
    for order in orders:
        items_total = sum(item["total_price"] for item in order["items"])

        # If order has items but is below minimum, try to top up
        while items_total > 0 and items_total < MIN_ORDER_TOTAL:
            candidates = [
                item for item in order["items"]
                if item["qty"] < product_stats[item["product"]]["max_per_order"]
                and item["unit_price"] > 0
            ]
            if not candidates:
                # Try adding new items from high-frequency products not yet in order
                existing_products = {item["product"] for item in order["items"]}
                new_candidates = [
                    (p, s) for p, s in product_stats.items()
                    if p not in existing_products
                    and s["unit_price"] > 0
                    and s["frequent"]
                ]
                if new_candidates:
                    # Add the highest-priced frequent item
                    new_candidates.sort(key=lambda x: -x[1]["unit_price"])
                    product, stats = new_candidates[0]
                    order["items"].append({
                        "product": product,
                        "qty": 1,
                        "unit_price": stats["unit_price"],
                        "total_price": stats["unit_price"],
                        "max_per_order": stats["max_per_order"],
                        "stock_before": 0,
                        "need_until_next": 0,
                        "topped_up": True,
                    })
                    items_total = sum(i["total_price"] for i in order["items"])
                else:
                    break
            else:
                candidate = max(candidates, key=lambda x: x["unit_price"])
                candidate["qty"] += 1
                candidate["total_price"] = candidate["qty"] * candidate["unit_price"]
                items_total = sum(i["total_price"] for i in order["items"])

        order["items_total"] = items_total
        order["total_with_delivery"] = items_total + DELIVERY_FEE if items_total > 0 else 0
        order["meets_minimum"] = items_total >= MIN_ORDER_TOTAL


def consolidate_small_orders(orders):
    """Merge orders that are too small into adjacent orders to meet minimums."""
    # Skip orders with no items
    valid_orders = [o for o in orders if o["items"]]

    # If an order doesn't meet minimum, try to merge with next order
    i = 0
    while i < len(valid_orders) - 1:
        if not valid_orders[i]["meets_minimum"]:
            # Merge into next order
            next_order = valid_orders[i + 1]
            for item in valid_orders[i]["items"]:
                # Check if product already in next order
                existing = next((x for x in next_order["items"] if x["product"] == item["product"]), None)
                if existing:
                    existing["qty"] += item["qty"]
                    existing["total_price"] = existing["qty"] * existing["unit_price"]
                else:
                    next_order["items"].append(item)
            next_order["notes"].append(f"Merged from {valid_orders[i]['date'].strftime('%Y-%m-%d')}")
            valid_orders[i]["items"] = []
            valid_orders[i]["items_total"] = 0
            valid_orders[i]["total_with_delivery"] = 0
            valid_orders[i]["skipped"] = True
        i += 1

    return orders


def print_weekly_plan(orders, product_stats, last_invoice_date, prediction_start, horizon_end):
    if not orders:
        print("No predicted orders found to build a weekly plan.")
        return

    print(f"\n{'='*80}")
    print(f"GROCERY ORDER PREDICTION - MINIMAL STOCK STRATEGY")
    print(f"{'='*80}")
    print(f"\nLast invoice date: {last_invoice_date.strftime('%A, %d %B %Y')}")
    print(f"Prediction starts: {prediction_start.strftime('%A, %d %B %Y')}")
    print(f"Days since last order: {(prediction_start - last_invoice_date).days}")
    print(f"Planning horizon ends: {horizon_end.strftime('%A, %d %B %Y')} (30 days from last invoice)")
    print(f"\nStrategy: {ORDERS_PER_WEEK} orders/week ({', '.join(ORDER_DAYS)})")
    print(f"Minimum order: ${MIN_ORDER_TOTAL}, Delivery fee: ${DELIVERY_FEE:.2f}")

    # Print PROMOTIONAL STRATEGY section
    print(f"\n{'='*80}")
    print("COLES PROMOTIONAL PATTERN ANALYSIS")
    print(f"{'='*80}")
    print(f"""
BEST DAYS TO ORDER (based on your history):
  1. TUESDAY  - 60% discount rate (new Coles specials often start Wed)
  2. FRIDAY   - 50% discount rate
  3. SATURDAY - 44% discount rate (weekend specials)

BEST WEEKS OF MONTH:
  1. Week 5 (Days 29-31) - 55% discount rate (end-of-month clearance)
  2. Week 2 (Days 8-14)  - 44% discount rate

AVOID: Week 4 (Days 22-28) - Only 20% discount rate

Current order schedule: {', '.join(ORDER_DAYS)} (optimized for discounts)
""")

    # Print PRICE PATTERNS section - items with promotional pricing
    promo_products = sorted(
        [(p, s) for p, s in product_stats.items() if s.get("has_promos", False)],
        key=lambda x: -x[1].get("price_variance_pct", 0)
    )
    promo_col_width = max(
        35,
        min(80, max((len(p[0]) for p in promo_products[:15]), default=0) + 2)
    )

    if promo_products:
        print(f"{'='*80}")
        print("PRODUCT-SPECIFIC DISCOUNT PATTERNS")
        print(f"{'='*80}")
        print(f"\n{'Product':<{promo_col_width}} | {'Save':<6} | {'Min$':<6} | {'Max$':<6} | {'Best Days':<15}")
        print("-" * (promo_col_width + 45))
        for product, stats in promo_products[:15]:
            savings = stats['max_price'] - stats['min_price']
            best_days = ', '.join(stats.get('best_days', [])[:2]) if stats.get('best_days') else 'N/A'
            print(
                f"{product:<{promo_col_width}} | "
                f"${savings:<5.2f} | "
                f"${stats['min_price']:<5.2f} | "
                f"${stats['max_price']:<5.2f} | "
                f"{best_days:<15}"
            )

    # Print product consumption summary - ALL products sorted by days until empty
    print(f"\n{'-'*80}")
    print("CURRENT STOCK LEVELS (sorted by urgency)")
    print(f"{'-'*80}")

    all_products = sorted(
        product_stats.items(),
        key=lambda x: x[1]["days_until_empty"]
    )

    stock_col_width = max(
        40,
        min(80, max((len(p[0]) for p in all_products), default=0) + 2)
    )

    print(f"\n{'Product':<{stock_col_width}} | {'Stock':<6} | {'Days':<8} | {'Avg/wk':<7} | {'Avg/ord':<7} | {'$/unit':<7} | {'Note'}")
    print("-" * (stock_col_width + 58))
    for product, stats in all_products[:40]:  # Show top 40
        days_left = stats["days_until_empty"]
        if days_left == float('inf'):
            days_str = "N/A"
        else:
            days_str = f"{days_left:.1f}"

        # Status note
        notes = []
        if days_left < 2:
            notes.append("URGENT!")
        elif days_left < 7:
            notes.append("Low")
        elif stats.get("has_promos"):
            notes.append("Promo")

        # Add marker if using actual stock
        if stats.get("stock_source") == "actual":
            notes.append("✓actual")

        note = ", ".join(notes) if notes else ""

        print(
            f"{product:<{stock_col_width}} | "
            f"{stats['estimated_stock']:<6.1f} | "
            f"{days_str:<8} | "
            f"{stats['weekly_need']:<7.2f} | "
            f"{stats['avg_qty_per_order']:<7.2f} | "
            f"${stats['unit_price']:<6.2f} | "
            f"{note}"
        )

    # Print promotional item tracking summary
    print(f"\n{'='*80}")
    print("PROMOTIONAL ITEM TRACKING - BUY ON THESE DATES")
    print(f"{'='*80}")

    # Collect all promotional items that appear in orders
    promo_items_in_orders = {}
    for order in orders:
        if order.get("skipped") or not order["items"]:
            continue
        for item in order["items"]:
            product = item["product"]
            pstats = product_stats.get(product, {})
            if pstats.get("has_promos"):
                if product not in promo_items_in_orders:
                    promo_items_in_orders[product] = {
                        "dates": [],
                        "best_days": pstats.get("best_days", []),
                        "min_price": pstats.get("min_price", 0),
                        "current_price": pstats.get("unit_price", 0),
                        "savings": pstats.get("max_price", 0) - pstats.get("min_price", 0)
                    }
                promo_items_in_orders[product]["dates"].append(order["date"])

    if promo_items_in_orders:
        print(f"\nItems with promotional patterns (buy when on sale for best value):")
        print(f"\n{'Product':<50} | {'Order Dates':<30} | {'Best Days':<15} | {'Save'}")
        print("-" * 115)

        for product, info in sorted(promo_items_in_orders.items(), key=lambda x: -x[1]["savings"]):
            dates_str = ", ".join([d.strftime("%b %d") for d in info["dates"][:3]])
            if len(info["dates"]) > 3:
                dates_str += f" +{len(info['dates'])-3} more"
            best_days_str = ", ".join(info["best_days"][:2]) if info["best_days"] else "N/A"

            # Check if current price is at minimum
            on_sale_now = " (ON SALE NOW!)" if info["current_price"] <= info["min_price"] else ""

            print(
                f"{product:<50} | "
                f"{dates_str:<30} | "
                f"{best_days_str:<15} | "
                f"${info['savings']:.2f}{on_sale_now}"
            )

        print(f"\nTip: Stock up on promotional items when they're at their lowest price!")
        print(f"     Historical data shows best discounts typically on: {', '.join(BEST_DISCOUNT_DAYS)}")

    # Print order schedule
    print(f"\n{'='*80}")
    print("ORDER SCHEDULE")
    print(f"{'='*80}")

    total_spend = 0
    orders_placed = 0
    order_product_names = [
        item["product"]
        for order in orders
        if not order.get("skipped")
        for item in order["items"]
    ]
    order_product_col_width = max(
        42,
        min(80, max((len(name) for name in order_product_names), default=0) + 2)
    )

    week_count = math.ceil(len(orders) / ORDERS_PER_WEEK) if orders else 0

    for week in range(week_count):
        start = week * ORDERS_PER_WEEK
        end = start + ORDERS_PER_WEEK
        week_orders = orders[start:end]
        week_total = 0

        print(f"\n{'─'*40}")
        print(f"WEEK {week + 1}")
        print(f"{'─'*40}")

        for order in week_orders:
            if order.get("skipped") or not order["items"]:
                print(f"\n  {order['date'].strftime('%A, %d %B %Y')}: SKIPPED (merged with next)")
                continue

            items_total = order.get("items_total", 0)
            if items_total == 0:
                continue

            week_total += order.get("total_with_delivery", 0)
            orders_placed += 1
            status = "OK" if order.get("meets_minimum") else "BELOW MIN"

            print(f"\n  ORDER DATE: {order['date'].strftime('%A, %d %B %Y')}")
            print(f"  Status: [{status}] | Items: ${items_total:.2f} | With delivery: ${order.get('total_with_delivery', 0):.2f}")

            if order.get("notes"):
                for note in order["notes"]:
                    print(f"  Note: {note}")

            print(f"\n  {'Product':<{order_product_col_width}} | {'Qty':<4} | {'$Unit':<7} | {'$Total':<7} | Notes")
            print("  " + "-" * (order_product_col_width + 32))

            for item in sorted(order["items"], key=lambda x: -x["total_price"]):
                notes = []
                if item.get("topped_up"):
                    notes.append("top-up")
                elif item.get("stock_before", 0) < 0.5:
                    notes.append("restock")

                # Check if item has promo pricing
                pstats = product_stats.get(item["product"], {})
                if pstats.get("has_promos"):
                    if item["unit_price"] <= pstats.get("min_price", item["unit_price"]):
                        notes.append("ON SALE!")
                    else:
                        notes.append(f"sale@${pstats.get('min_price', 0):.2f}")

                print(
                    f"  {item['product']:<{order_product_col_width}} | "
                    f"{item['qty']:<4} | "
                    f"${item['unit_price']:<6.2f} | "
                    f"${item['total_price']:<6.2f} | "
                    f"{', '.join(notes)}"
                )

            # Add reorder prompt
            print(f"\n  Reorder via https://www.coles.com.au")
            print(f"  these items:")
            for item in sorted(order["items"], key=lambda x: -x["total_price"]):
                # Remove % prefix if present (indicates promotional/special item)
                product_name = item['product'].lstrip('%')
                print(f"  {product_name} x{item['qty']}")

        total_spend += week_total
        if week_total > 0:
            print(f"\n  Week {week + 1} total: ${week_total:.2f}")

    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"Total orders planned: {orders_placed}")
    print(f"Total spend (with delivery): ${total_spend:.2f}")
    print(f"Average per order: ${total_spend/orders_placed:.2f}" if orders_placed > 0 else "")
    print(f"Delivery fees: ${DELIVERY_FEE * orders_placed:.2f}")


def predict_two_dollar_delivery_orders():
    df_grouped, product_prices, last_invoice_date, price_history = load_grouped_orders()
    if df_grouped is None:
        print("No data found to predict.")
        return

    print(f"Loaded {len(df_grouped)} grouped records across {df_grouped['product'].nunique()} products.")

    if last_invoice_date is None:
        print("Could not determine last invoice date.")
        return

    # Load in-stock data
    in_stock_dict, stock_date = load_in_stock()

    # Analyze price patterns to detect promotions
    promo_info = analyze_price_patterns(price_history)
    promo_count = sum(1 for p in promo_info.values() if p.get("has_promos", False))
    print(f"Analyzed price history: {len(price_history)} products, {promo_count} with promotional patterns.")

    # Plan for one month from the last invoice date
    horizon_end = last_invoice_date + timedelta(days=PREDICTION_WINDOW_DAYS)
    today = pd.Timestamp.now().normalize()
    prediction_start = max(today, last_invoice_date + timedelta(days=1))
    if prediction_start > horizon_end:
        print(f"Last invoice is over {PREDICTION_WINDOW_DAYS} days old; no forward window to plan.")
        return

    product_stats = compute_product_stats(df_grouped, product_prices, last_invoice_date, prediction_start, promo_info, in_stock_dict, stock_date)
    if not product_stats:
        print("No products with measurable demand.")
        return

    order_dates = generate_order_dates(prediction_start, horizon_end)
    if not order_dates:
        print("No order dates fall within the one-month planning window.")
        return
    orders = build_minimal_orders(product_stats, order_dates, prediction_start)
    enforce_minimums(orders, product_stats)
    consolidate_small_orders(orders)

    # Recalculate totals after consolidation
    for order in orders:
        if not order.get("skipped"):
            order["items_total"] = sum(item["total_price"] for item in order["items"])
            order["total_with_delivery"] = order["items_total"] + DELIVERY_FEE if order["items_total"] > 0 else 0
            order["meets_minimum"] = order["items_total"] >= MIN_ORDER_TOTAL

    print_weekly_plan(orders, product_stats, last_invoice_date, prediction_start, horizon_end)


if __name__ == "__main__":
    predict_two_dollar_delivery_orders()
