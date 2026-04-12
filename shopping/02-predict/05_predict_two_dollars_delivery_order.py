import argparse
import html
import json
import logging
import os
import math
from datetime import timedelta

import pandas as pd

# Suppress noisy logs from Prophet dependency if it is installed
logging.getLogger("cmdstanpy").setLevel(logging.ERROR)
logging.getLogger("prophet").setLevel(logging.ERROR)

# ANSI color codes
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

def green(text):
    return f"{Colors.GREEN}{text}{Colors.RESET}"

def red(text):
    return f"{Colors.RED}{text}{Colors.RESET}"

def yellow(text):
    return f"{Colors.YELLOW}{text}{Colors.RESET}"

def cyan(text):
    return f"{Colors.CYAN}{text}{Colors.RESET}"

def bold(text):
    return f"{Colors.BOLD}{text}{Colors.RESET}"

OUTPUT_DIR = "output_extracted"
MIN_ORDER_TOTAL = 50  # Coles minimum order requirement
DELIVERY_FEE = 2.0    # assumed flat delivery fee per order
ORDERS_PER_WEEK = 2   # optimal for catching discounts
# Based on analysis: Tuesday (60% discount rate) and Saturday (44% discount rate)
ORDER_DAYS = ["Tuesday", "Saturday"]  # best days for Coles discounts
ORDER_OFFSETS = [1, 5]  # Tuesday=1, Saturday=5 (Monday=0)
PREDICTION_WINDOW_DAYS = 21  # plan 3 weeks ahead from last invoice

# Promotional pattern insights from historical data
BEST_DISCOUNT_DAYS = ["Tuesday", "Friday", "Saturday"]
BEST_DISCOUNT_WEEKS = [1, 2, 5]  # Week of month (1=days 1-7, 5=days 29-31)
WORST_DISCOUNT_WEEK = 4  # Days 22-28 - avoid if possible


def load_in_stock():
    """Load in-stock data from in-stock.json and return a dict with fuzzy-matched product names."""
    stock_file = os.path.join(OUTPUT_DIR, "in-stock.json")
    if not os.path.exists(stock_file):
        print(yellow(f"Note: {stock_file} not found. Using estimated stock levels."))
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

        print(green(f"Loaded in-stock data from {stock_date.strftime('%Y-%m-%d') if stock_date else 'unknown date'}: {len(in_stock)} items"))
        return in_stock, stock_date
    except Exception as e:
        print(red(f"Warning: Error loading in-stock.json: {e}"))
        return {}, None


def load_dont_order():
    """Load products that should not be ordered from dont-order.json"""
    dont_order_file = os.path.join(OUTPUT_DIR, "dont-order.json")
    if os.path.exists(dont_order_file):
        with open(dont_order_file, "r") as f:
            data = json.load(f)
            return set(data.get("items", []))
    return set()


def load_generic_products():
    """Load generic product mappings"""
    generic_file = os.path.join(OUTPUT_DIR, "generic-products.json")
    if os.path.exists(generic_file):
        with open(generic_file, "r") as f:
            data = json.load(f)
            return data.get("mappings", {})
    return {}


def find_generic_product(product, generic_mappings):
    """Find the generic product name for a specific product"""
    for generic_name, products in generic_mappings.items():
        if product in products:
            return generic_name
    return None


def _norm(s):
    """Normalize apostrophes and case for matching."""
    return s.replace("''", "'").replace("\u2019", "'").lower().strip()


def is_product_blocked(product, dont_order_set, generic_mappings):
    """Check if product or its generic group is in dont-order list"""
    # Direct match
    if product in dont_order_set:
        return True

    product_norm = _norm(product)

    # Normalized / partial / substring match
    for blocked in dont_order_set:
        blocked_norm = _norm(blocked)
        if (product_norm == blocked_norm
                or product_norm.startswith(blocked_norm)
                or blocked_norm.startswith(product_norm)
                or blocked_norm in product_norm):
            return True

    # Check if any product in same generic group is blocked
    generic_name = find_generic_product(product, generic_mappings)
    if generic_name:
        for p in generic_mappings[generic_name]:
            if p in dont_order_set:
                return True
            p_norm = _norm(p)
            for blocked in dont_order_set:
                blocked_norm = _norm(blocked)
                if (p_norm == blocked_norm
                        or p_norm.startswith(blocked_norm)
                        or blocked_norm.startswith(p_norm)
                        or blocked_norm in p_norm):
                    return True

    return False


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
        print(red(f"Error: {data_file} not found. Please run extraction first."))
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


def calculate_consumption_metrics(df, oldest_invoice_date):
    """
    Calculate consumption metrics for a dataset (single product or group).
    df: DataFrame with 'ds' (date) and 'y' (quantity) columns.
    Returns: daily_rate, avg_interval, avg_qty_per_order, last_date, last_order_qty, total_qty, order_count, excluded_rows
    """
    # Ensure sorted
    df = df.sort_values("ds")

    excluded_rows = []

    # Anomaly detection: exclude upper outlier quantities (accidental large orders)
    if len(df) >= 3:
        quantities = df["y"]
        median_val = quantities.median()

        if median_val > 0:
            if len(df) <= 5:
                upper_bound = median_val * 3.0
            else:
                q1 = quantities.quantile(0.25)
                q3 = quantities.quantile(0.75)
                iqr = q3 - q1
                iqr_bound = (q3 + 1.5 * iqr) if iqr > 0 else q3
                upper_bound = max(iqr_bound, median_val * 2.5)

            outlier_mask = quantities > upper_bound
            if outlier_mask.any():
                for idx in df[outlier_mask].index:
                    row = df.loc[idx]
                    excluded_rows.append({
                        "date": row["ds"],
                        "qty": row["y"],
                        "threshold": upper_bound,
                        "median": median_val,
                    })
                    print(yellow(
                        f"  Anomaly detected: qty={row['y']:.0f} on "
                        f"{row['ds'].strftime('%Y-%m-%d')} "
                        f"(threshold={upper_bound:.1f}, median={median_val:.1f})"
                        f" -- excluded from consumption calc"
                    ))
                df = df[~outlier_mask].copy()

    total_qty = df["y"].sum()
    order_count = len(df)

    if order_count == 0:
        return 0, 0, 0, None, 0, 0, 0, excluded_rows

    first_date = df["ds"].min()
    last_date = df["ds"].max()
    
    # Last order qty (sum of all items on the last date)
    last_order_qty = df[df["ds"] == last_date]["y"].sum()

    avg_qty_per_order = total_qty / order_count
    
    # Calculate intervals
    avg_interval = None
    if order_count > 1:
        # Calculate days between orders
        # Note: If multiple rows have same date, diff() gives 0, which is correct for "same day" orders
        # but we might want unique dates for interval calculation
        unique_dates = sorted(df["ds"].unique())
        if len(unique_dates) > 1:
            intervals = pd.Series(unique_dates).diff().dt.days.dropna()
            avg_interval = intervals.mean()

    # Daily Rate Logic
    daily_rate = 0
    if order_count >= 2:
        # Multiple orders: calculate from first order to last order
        total_period = (last_date - first_date).days
        if total_period > 0:
            daily_rate = total_qty / total_period
        elif avg_interval and avg_interval > 0:
            daily_rate = avg_qty_per_order / avg_interval
        else:
            daily_rate = avg_qty_per_order / 7  # Default to weekly
    else:
        # Single order: consumption period is from oldest invoice to this order
        total_period = (last_date - oldest_invoice_date).days
        if total_period > 0:
            daily_rate = total_qty / total_period
        else:
            # Order is on the oldest invoice date - default to weekly consumption
            daily_rate = total_qty / 7
            
    return daily_rate, avg_interval, avg_qty_per_order, last_date, last_order_qty, total_qty, order_count, excluded_rows


def compute_product_stats(df_grouped, product_prices, last_invoice_date, prediction_start, promo_info=None, in_stock_dict=None, stock_date=None, generic_mappings=None, dont_order_set=None):
    """Calculate daily consumption and estimate current stock levels.

    Improved Logic:
    - Aggregates "Generic Product Groups" first to calculate pooled consumption and stock.
    - Selects a "Representative" product for the group (prioritizing items on sale).
    - Prevents "0 stock" bugs where switching brands caused the system to think you were out.
    """
    # DEBUG: Products to trace
    DEBUG_PRODUCTS = [
        "%Swisse Ultivite Women''s Multivitamin With Key Nut",
        "Foaming",
        "Handwash"
    ]
    
    stats = {}
    promo_info = promo_info or {}
    in_stock_dict = in_stock_dict or {}
    generic_mappings = generic_mappings or {}
    dont_order_set = dont_order_set or set()

    # Find the oldest invoice date across all products (global baseline)
    oldest_invoice_date = df_grouped["ds"].min()

    # Map products to their groups
    product_to_group = {}
    for g_name, p_list in generic_mappings.items():
        for p in p_list:
            product_to_group[p] = g_name

    processed_products = set()

    # =========================================================
    # 1. PROCESS GENERIC GROUPS
    # =========================================================
    for group_name, group_products in generic_mappings.items():
        # Get data for all products in this group
        # Filter df_grouped for products in this group
        group_df = df_grouped[df_grouped["product"].isin(group_products)].copy()
        
        if group_df.empty:
            continue

        # Mark these products as processed
        processed_products.update(group_df["product"].unique())

        # Aggregate data: Group by Date only (summing quantities across different brands/types)
        # We create a "Virtual Product" history for the group
        group_daily_df = group_df.groupby("ds")["y"].sum().reset_index()

        # Calculate metrics for the GROUP
        daily_rate, avg_interval, avg_qty_per_order, last_date, last_order_qty, total_qty, order_count, _ = \
            calculate_consumption_metrics(group_daily_df, oldest_invoice_date)

        if total_qty <= 0 or daily_rate <= 0:
            continue

        # Determine if frequent
        weekly_need = daily_rate * 7
        frequent = False
        if order_count >= 3 and avg_interval is not None and avg_interval <= 14:
            frequent = True
        elif weekly_need >= 0.5:
            frequent = True

        # Calculate Group Actual Stock (Sum of all matches)
        actual_stock = 0
        has_actual_stock = False
        for p in group_products:
            qty = match_product_to_stock(p, in_stock_dict)
            if qty is not None:
                actual_stock += qty
                has_actual_stock = True

        # Estimate Stock
        stock_source = "estimated"
        if has_actual_stock and stock_date:
            days_since_stock_date = (prediction_start - stock_date).days
            consumed_since_stock_date = daily_rate * days_since_stock_date
            estimated_stock = max(0, actual_stock - consumed_since_stock_date)
            stock_source = "actual"
        else:
            days_since_last_order = (prediction_start - last_date).days
            consumed_since_last = daily_rate * days_since_last_order
            estimated_stock = max(0, last_order_qty - consumed_since_last)
            
        days_until_empty = estimated_stock / daily_rate if daily_rate > 0 else float('inf')

        # SELECT REPRESENTATIVE PRODUCT
        # We need to choose which specific product to put on the shopping list.
        # Criteria:
        # 1. Not in 'dont_order_set' (Strong preference)
        # 2. Currently ON SALE (Best value)
        # 3. Has Promos (Good habit)
        # 4. Most frequently bought (Habit)

        candidates = [p for p in group_products if p in product_prices]
        if not candidates:
             # Fallback to any product in the group data
             candidates = group_df["product"].unique()

        best_candidate = candidates[0]
        best_score = -float('inf')

        for p in candidates:
            score = 0
            pinfo = promo_info.get(p, {})
            current_price = product_prices.get(p, {}).get("price", 0)
            
            # Penalize blocked items heavily
            if is_product_blocked(p, dont_order_set, generic_mappings):
                score -= 10000

            # Bonus for being on sale NOW
            min_price = pinfo.get("min_price", 0)
            if pinfo.get("has_promos") and current_price <= min_price * 1.05 and current_price > 0:
                score += 500
            
            # Bonus for having promo patterns generally
            if pinfo.get("has_promos"):
                score += 50

            # Bonus for frequency (count of rows in original df for this specific product)
            p_rows = len(group_df[group_df["product"] == p])
            score += p_rows

            if score > best_score:
                best_score = score
                best_candidate = p

        representative = best_candidate
        
        # Get unit price of the representative
        unit_price = product_prices.get(representative, {}).get("price", 0)
        
        # Max per order: heuristic based on group behavior
        max_per_order = max(1, math.ceil(avg_qty_per_order))
        rep_pinfo = promo_info.get(representative, {})
        if rep_pinfo.get("has_promos"):
            max_per_order = max(max_per_order, rep_pinfo.get("promo_stock_up", max_per_order))

        stats[representative] = {
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
            "days_since_last_order": (prediction_start - last_date).days,
            "stock_source": stock_source,
            "is_group_representative": True,
            "group_name": group_name,
            # Promo info (from Representative)
            "has_promos": rep_pinfo.get("has_promos", False),
            "min_price": rep_pinfo.get("min_price", unit_price),
            "max_price": rep_pinfo.get("max_price", unit_price),
            "avg_price": rep_pinfo.get("avg_price", unit_price),
            "price_variance_pct": rep_pinfo.get("price_variance_pct", 0),
            "promo_stock_up": rep_pinfo.get("promo_stock_up", max_per_order),
            "savings_pct": rep_pinfo.get("savings_pct", 0),
            "best_days": rep_pinfo.get("best_days", []),
            "best_weeks": rep_pinfo.get("best_weeks", []),
        }

    # =========================================================
    # 2. PROCESS INDIVIDUAL PRODUCTS
    # =========================================================
    for product in df_grouped["product"].unique():
        if product in processed_products:
            continue
        
        # DEBUG: Check if this is a target product
        is_debug_product = any(debug.lower() in product.lower() or product.lower() in debug.lower() for debug in DEBUG_PRODUCTS)
            
        # Standard individual processing
        product_df = df_grouped[df_grouped["product"] == product]
        
        # Calculate consumption metrics
        daily_rate, avg_interval, avg_qty_per_order, last_date, last_order_qty, total_qty, order_count, _ = \
            calculate_consumption_metrics(product_df, oldest_invoice_date)
            
        if total_qty <= 0: 
            if is_debug_product:
                print(red(f"DEBUG: '{product}' skipped in compute_product_stats - total_qty <= 0"))
            continue

        # Skip free/promotional items (price 0)
        unit_price = product_prices.get(product, {}).get("price", 0.0)
        if unit_price == 0:
            if is_debug_product:
                print(red(f"DEBUG: '{product}' skipped in compute_product_stats - unit_price == 0"))
            continue
            
        # Skip old one-time purchases
        days_since_last_order = (prediction_start - last_date).days
        if order_count < 2 and days_since_last_order > 30:
            if is_debug_product:
                print(red(f"DEBUG: '{product}' skipped in compute_product_stats - one-time purchase >30 days old (order_count={order_count}, days_since_last={days_since_last_order})"))
            continue

        weekly_need = daily_rate * 7
        
        frequent = False
        if order_count >= 3 and avg_interval is not None and avg_interval <= 14:
            frequent = True
        elif weekly_need >= 0.5:
            frequent = True

        max_per_order = max(1, math.ceil(avg_qty_per_order))
        pinfo = promo_info.get(product, {})
        has_promos = pinfo.get("has_promos", False)
        promo_stock_up = pinfo.get("promo_stock_up", max_per_order)
        if has_promos:
            max_per_order = max(max_per_order, promo_stock_up)

        # Stock Estimation
        actual_stock = match_product_to_stock(product, in_stock_dict)
        stock_source = "estimated"
        
        if actual_stock is not None and stock_date:
            days_since_stock_date = (prediction_start - stock_date).days
            consumed_since_stock_date = daily_rate * days_since_stock_date
            estimated_stock = max(0, actual_stock - consumed_since_stock_date)
            stock_source = "actual"
            
            if is_debug_product:
                print(cyan(f"\nDEBUG: Stock calculation for '{product}':"))
                print(f"  Actual stock (from {stock_date.strftime('%Y-%m-%d')}): {actual_stock}")
                print(f"  Days since stock date: {days_since_stock_date}")
                print(f"  Daily consumption rate: {daily_rate:.4f}")
                print(f"  Consumed since stock date: {consumed_since_stock_date:.2f}")
                print(f"  Estimated current stock: {estimated_stock:.2f}")
        else:
            consumed_since_last = daily_rate * days_since_last_order
            estimated_stock = max(0, last_order_qty - consumed_since_last)
            
            if is_debug_product:
                print(cyan(f"\nDEBUG: Stock calculation for '{product}' (no actual stock data):"))
                print(f"  Last order quantity: {last_order_qty}")
                print(f"  Days since last order: {days_since_last_order}")
                print(f"  Daily consumption rate: {daily_rate:.4f}")
                print(f"  Consumed since last: {consumed_since_last:.2f}")
                print(f"  Estimated current stock: {estimated_stock:.2f}")

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
            "stock_source": stock_source,
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
    # DEBUG: Products to trace
    DEBUG_PRODUCTS = [
        "%Swisse Ultivite Women''s Multivitamin With Key Nut",
        "Foaming",
        "Handwash"
    ]
    
    orders = [{"date": d, "items": [], "notes": []} for d in order_dates]
    
    if not orders:
        return orders

    # Separate URGENT items (0 stock) from regular items
    urgent_products = []
    regular_products = []
    
    for product, stats in product_stats.items():
        # URGENT: products with 0 or near-0 stock (less than 1 day supply)
        if stats["estimated_stock"] <= 0 or stats["days_until_empty"] < 1:
            urgent_products.append((product, stats))
        else:
            regular_products.append((product, stats))
    
    # Sort urgent by weekly need (most consumed first)
    urgent_products.sort(key=lambda x: -x[1]["weekly_need"])
    
    # Add ALL urgent items to the FIRST order
    first_order = orders[0]
    for product, stats in urgent_products:
        daily_rate = stats["daily_rate"]
        if daily_rate <= 0:
            continue
            
        # For urgent items, order enough to last until second order (or longer)
        if len(orders) > 1:
            days_to_cover = (orders[1]["date"] - first_order["date"]).days
        else:
            days_to_cover = 7  # Default to 1 week if only one order
            
        # Calculate quantity needed
        needed = daily_rate * days_to_cover
        qty_to_order = max(1, math.ceil(needed))
        
        # Cap at historical maximum or double the average
        max_per_order = stats["max_per_order"]
        avg_qty = stats["avg_qty_per_order"]
        effective_max = max(max_per_order, math.ceil(avg_qty * 2))
        qty_to_order = min(qty_to_order, effective_max)
        
        unit_price = stats["unit_price"]
        first_order["items"].append({
            "product": product,
            "qty": qty_to_order,
            "unit_price": unit_price,
            "total_price": qty_to_order * unit_price,
            "max_per_order": max_per_order,
            "stock_before": 0.0,
            "need_until_next": round(needed, 1),
            "urgent": True,
        })
    
    # Sort regular products by urgency (days until empty)
    sorted_products = sorted(
        regular_products,
        key=lambda x: (x[1]["days_until_empty"], -x[1]["weekly_need"])
    )

    # For each regular product, calculate when it will run out and schedule orders accordingly
    for product, stats in sorted_products:
        # DEBUG: Check if this is a target product
        is_debug_product = any(debug.lower() in product.lower() or product.lower() in debug.lower() for debug in DEBUG_PRODUCTS)
        
        daily_rate = stats["daily_rate"]
        if daily_rate <= 0:
            if is_debug_product:
                print(red(f"DEBUG: '{product}' skipped - daily_rate <= 0 ({daily_rate})"))
            continue

        # Skip items with very low consumption (less than 1 unit per month)
        if stats["weekly_need"] < 0.1:
            if is_debug_product:
                print(red(f"DEBUG: '{product}' skipped - weekly_need < 0.1 ({stats['weekly_need']:.3f})"))
            continue

        unit_price = stats["unit_price"]
        max_per_order = stats["max_per_order"]
        estimated_stock = stats["estimated_stock"]

        # Track stock level as we go through order dates
        current_stock = estimated_stock
        last_order_date = start_date
        
        if is_debug_product:
            print(cyan(f"\nDEBUG: Processing '{product}':"))
            print(f"  Initial stock: {estimated_stock:.1f}")
            print(f"  Daily rate: {daily_rate:.3f}")
            print(f"  Weekly need: {stats['weekly_need']:.3f}")
            print(f"  Days until empty: {stats['days_until_empty']:.1f}")
            print(f"  Unit price: ${unit_price:.2f}")

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
                # Order enough to cover the shortfall AND last until the next order
                # This prevents re-ordering the same product in consecutive orders
                avg_qty = stats["avg_qty_per_order"]

                # Calculate minimum needed: at least cover shortfall, rounded up
                min_needed = math.ceil(shortfall)

                # Order the larger of: minimum needed OR typical order quantity
                qty_to_order = max(min_needed, max(1, round(avg_qty)))

                # Allow up to 2x historical max to cover longer periods between orders
                effective_max = max(max_per_order, min_needed)
                qty_to_order = min(qty_to_order, effective_max)

                # Check if this product is already in the order (from urgent items)
                existing_item = next((item for item in order["items"] if item["product"] == product), None)
                if existing_item:
                    # Product already added as urgent - skip
                    if is_debug_product:
                        print(yellow(f"  - Already in order on {order['date'].strftime('%Y-%m-%d')} (urgent item)"))
                    current_stock += existing_item["qty"]
                else:
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
                    
                    if is_debug_product:
                        print(green(f"  ✓ Added to order on {order['date'].strftime('%Y-%m-%d')}: {qty_to_order} units"))
            elif is_debug_product:
                print(f"  - Skipped order on {order['date'].strftime('%Y-%m-%d')}: stock={current_stock:.1f}, needed={needed_for_period:.1f}")

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


def consolidate_duplicate_products(orders, product_stats):
    """
    Remove duplicate products from consecutive orders.
    If a product appears in Order N and Order N+1, consolidate into Order N
    with enough quantity to last until Order N+2.
    """
    valid_orders = [o for o in orders if o["items"] and not o.get("skipped")]

    for i in range(len(valid_orders) - 1):
        current_order = valid_orders[i]
        next_order = valid_orders[i + 1]

        # Find products that appear in both orders
        current_products = {item["product"]: item for item in current_order["items"]}
        products_to_remove = []

        for item in next_order["items"]:
            product = item["product"]
            if product in current_products:
                # Product appears in both orders - consolidate into current order
                current_item = current_products[product]
                stats = product_stats.get(product, {})
                daily_rate = stats.get("daily_rate", 0)

                # Calculate days until order after next
                if i + 2 < len(valid_orders):
                    days_to_cover = (valid_orders[i + 2]["date"] - current_order["date"]).days
                else:
                    days_to_cover = (next_order["date"] - current_order["date"]).days + 7

                # Calculate total quantity needed
                total_needed = math.ceil(daily_rate * days_to_cover)
                combined_qty = current_item["qty"] + item["qty"]

                # Use the larger of: combined quantity or needed quantity
                new_qty = max(combined_qty, total_needed)

                # Update current order with consolidated quantity
                current_item["qty"] = new_qty
                current_item["total_price"] = new_qty * current_item["unit_price"]

                # Mark item for removal from next order
                products_to_remove.append(product)

        # Remove consolidated products from next order
        next_order["items"] = [item for item in next_order["items"] if item["product"] not in products_to_remove]

    return orders


def consolidate_small_orders(orders):
    """
    Aggressively merge orders that don't meet the minimum threshold.
    Strategy:
    1. Try to merge FORWARD (into the next order).
    2. If no next order (end of list), merge BACKWARD (into previous order).
    Repeat until all valid orders meet minimum or no merges are possible.
    """
    changed = True
    while changed:
        changed = False
        # Get indices of currently valid orders
        active_indices = [i for i, o in enumerate(orders) if o["items"] and not o.get("skipped")]
        
        for idx_in_active, i in enumerate(active_indices):
            order = orders[i]
            
            # Recalculate totals to ensure status is current
            items_total = sum(item["total_price"] for item in order["items"])
            order["items_total"] = items_total
            order["meets_minimum"] = items_total >= MIN_ORDER_TOTAL
            
            if not order["meets_minimum"]:
                target_idx = None
                direction = ""
                
                # 1. Try Merging Forward
                if idx_in_active < len(active_indices) - 1:
                    target_idx = active_indices[idx_in_active + 1]
                    direction = "forward"
                # 2. Try Merging Backward (only if forward not possible)
                elif idx_in_active > 0:
                    target_idx = active_indices[idx_in_active - 1]
                    direction = "backward"
                
                if target_idx is not None:
                    target_order = orders[target_idx]
                    
                    # Move items
                    for item in order["items"]:
                        existing = next((x for x in target_order["items"] if x["product"] == item["product"]), None)
                        if existing:
                            existing["qty"] += item["qty"]
                            existing["total_price"] = existing["qty"] * existing["unit_price"]
                        else:
                            target_order["items"].append(item)
                    
                    target_order["notes"].append(f"Merged {direction} from {order['date'].strftime('%Y-%m-%d')}")
                    
                    # Clear current order
                    order["items"] = []
                    order["items_total"] = 0
                    order["total_with_delivery"] = 0
                    order["skipped"] = True
                    
                    # Restart loop since indices changed
                    changed = True
                    break

    return orders


def print_weekly_plan(orders, product_stats, last_invoice_date, prediction_start, horizon_end):
    if not orders:
        print(red("No predicted orders found to build a weekly plan."))
        return

    print(green(f"\n{'='*80}"))
    print(green(bold(f"  GROCERY ORDER PREDICTION - MINIMAL STOCK STRATEGY")))
    print(green(f"{'='*80}"))
    print(f"\nLast invoice date: {last_invoice_date.strftime('%A, %d %B %Y')}")
    print(f"Prediction starts: {prediction_start.strftime('%A, %d %B %Y')}")
    print(f"Days since last order: {(prediction_start - last_invoice_date).days}")
    print(f"Planning horizon ends: {horizon_end.strftime('%A, %d %B %Y')} (3 weeks from last invoice)")
    print(f"\nStrategy: {ORDERS_PER_WEEK} orders/week ({', '.join(ORDER_DAYS)})")
    print(f"Minimum order: ${MIN_ORDER_TOTAL}, Delivery fee: ${DELIVERY_FEE:.2f}")

    # Print PROMOTIONAL STRATEGY section
    print(green(f"\n{'='*80}"))
    print(green(bold("  COLES PROMOTIONAL PATTERN ANALYSIS")))
    print(green(f"{'='*80}"))
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
        print(green(f"{'='*80}"))
        print(green(bold("  PRODUCT-SPECIFIC DISCOUNT PATTERNS")))
        print(green(f"{'='*80}"))
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
    print(green(f"\n{'-'*80}"))
    print(green(bold("  CURRENT STOCK LEVELS (sorted by urgency)")))
    print(green(f"{'-'*80}"))

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
        is_urgent = False
        if days_left < 2:
            notes.append("URGENT!")
            is_urgent = True
        elif days_left < 7:
            notes.append("Low")
        elif stats.get("has_promos"):
            notes.append("Promo")

        # Add marker if using actual stock
        if stats.get("stock_source") == "actual":
            notes.append("✓actual")

        note = ", ".join(notes) if notes else ""

        line = (
            f"{product:<{stock_col_width}} | "
            f"{stats['estimated_stock']:<6.1f} | "
            f"{days_str:<8} | "
            f"{stats['weekly_need']:<7.2f} | "
            f"{stats['avg_qty_per_order']:<7.2f} | "
            f"${stats['unit_price']:<6.2f} | "
            f"{note}"
        )
        if is_urgent:
            print(red(line))
        elif days_left < 7:
            print(yellow(line))
        else:
            print(line)

    # Print promotional item tracking summary
    print(green(f"\n{'='*80}"))
    print(green(bold("  PROMOTIONAL ITEM TRACKING - BUY ON THESE DATES")))
    print(green(f"{'='*80}"))

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
    print(green(f"\n{'='*80}"))
    print(green(bold("  ORDER SCHEDULE")))
    print(green(f"{'='*80}"))

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

        print(green(f"\n{'─'*40}"))
        print(green(bold(f"  WEEK {week + 1}")))
        print(green(f"{'─'*40}"))

        for order in week_orders:
            if order.get("skipped") or not order["items"]:
                print(yellow(f"\n  {order['date'].strftime('%A, %d %B %Y')}: SKIPPED (merged with next)"))
                continue

            items_total = order.get("items_total", 0)
            if items_total == 0:
                continue

            week_total += order.get("total_with_delivery", 0)
            orders_placed += 1

            # Check if order is soon (within 3 days) - mark as critical
            today = pd.Timestamp.now().normalize()
            days_until = (order['date'] - today).days
            is_urgent = days_until <= 3

            if order.get("meets_minimum"):
                status = green("[OK]")
            else:
                status = red("[BELOW MIN]")

            if is_urgent:
                print(red(bold(f"\n  ORDER DATE: {order['date'].strftime('%A, %d %B %Y')} (in {days_until} days!)")))
            else:
                print(green(f"\n  ORDER DATE: {order['date'].strftime('%A, %d %B %Y')}"))
            print(f"  Status: {status} | Items: ${items_total:.2f} | With delivery: ${order.get('total_with_delivery', 0):.2f}")

            if order.get("notes"):
                for note in order["notes"]:
                    print(f"  Note: {note}")

            print(f"\n  {'Product':<{order_product_col_width}} | {'Qty':<4} | {'$Unit':<7} | {'$Total':<7} | Notes")
            print("  " + "-" * (order_product_col_width + 32))
            
            # DEBUG: First order
            if week == 0 and order['date'] == orders[0]['date']:
                print(cyan(f"  DEBUG: Showing {len(order['items'])} items in first order"))

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

                # Highlight urgent items
                line = (
                    f"  {item['product']:<{order_product_col_width}} | "
                    f"{item['qty']:<4} | "
                    f"${item['unit_price']:<6.2f} | "
                    f"${item['total_price']:<6.2f} | "
                    f"{', '.join(notes)}"
                )
                if item.get("urgent"):
                    print(red(line))
                else:
                    print(line)

            # Add reorder prompt (outside the item loop)
            print(f"\n  Reorder via https://www.coles.com.au")
            print(f"  these items:")
            for item in sorted(order["items"], key=lambda x: -x["total_price"]):
                # Remove % prefix if present (indicates promotional/special item)
                product_name = item['product'].lstrip('%')
                print(f"  {product_name} x{item['qty']}")

        total_spend += week_total
        if week_total > 0:
            print(f"\n  Week {week + 1} total: ${week_total:.2f}")

    print(green(f"\n{'='*80}"))
    print(green(bold("  SUMMARY")))
    print(green(f"{'='*80}"))
    print(f"Total orders planned: {orders_placed}")
    print(f"Total spend (with delivery): ${total_spend:.2f}")
    print(f"Average per order: ${total_spend/orders_placed:.2f}" if orders_placed > 0 else "")
    print(f"Delivery fees: ${DELIVERY_FEE * orders_placed:.2f}")
    print(green(f"\n{'─'*40}"))
    print(green(bold(f"  TOTAL: ${total_spend:.2f}")))


def _safe_money(value):
    try:
        return f"${float(value):.2f}"
    except Exception:
        return "$0.00"


def _format_date(dt):
    if dt is None:
        return ""
    try:
        return pd.to_datetime(dt).strftime("%A, %d %B %Y")
    except Exception:
        return str(dt)


def _build_reorder_prompt(order):
    # Kept intentionally simple so it works as a reusable "prompt" anywhere.
    lines = []
    order_date = order.get("date")
    if order_date is not None:
        lines.append(f"ORDER DATE: {pd.to_datetime(order_date).strftime('%A, %d %B %Y')}")
        lines.append("")
    lines.append("Reorder via https://www.coles.com.au")
    lines.append("these items:")
    for item in sorted(order.get("items", []), key=lambda x: -x.get("total_price", 0)):
        product_name = str(item.get("product", "")).lstrip("%").strip()
        qty = item.get("qty", 0)
        lines.append(f"{product_name} x{qty}")
    return "\n".join(lines).strip() + "\n"


def write_html_report(orders, product_stats, last_invoice_date, prediction_start, horizon_end, output_path):
    """
    Write a standalone HTML report with:
    - clean, readable tables per order
    - a textarea "prompt" per order + copy button
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    today = pd.Timestamp.now().normalize()
    generated_at = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")

    active_orders = [o for o in orders if not o.get("skipped") and o.get("items")]
    skipped_orders = [o for o in orders if o.get("skipped")]

    orders_placed = len(active_orders)
    total_spend = sum(float(o.get("total_with_delivery", 0) or 0) for o in active_orders)
    delivery_fees = DELIVERY_FEE * orders_placed

    def badge(text, kind):
        return f'<span class="badge badge-{kind}">{html.escape(text)}</span>'

    parts = []
    parts.append("<!doctype html>")
    parts.append('<html lang="en">')
    parts.append("<head>")
    parts.append('  <meta charset="utf-8" />')
    parts.append('  <meta name="viewport" content="width=device-width, initial-scale=1" />')
    parts.append("  <title>Coles Order Plan</title>")
    parts.append("  <style>")
    parts.append("""
:root{
  --bg0:#fbf4e8;
  --bg1:#e8f2f0;
  --ink:#161816;
  --muted:#4b514b;
  --card:rgba(255,255,255,.74);
  --line:rgba(22,24,22,.12);
  --shadow:0 18px 60px rgba(22,24,22,.12);
  --accent:#1f7a74;
  --accent2:#c66a2f;
  --ok:#1f6f3b;
  --warn:#a06000;
  --bad:#a61b2b;
  --radius:18px;
  --mono:ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
}
*{box-sizing:border-box}
html,body{height:100%}
body{
  margin:0;
  color:var(--ink);
  background:
    radial-gradient(1200px 650px at 12% 6%, rgba(31,122,116,.22), transparent 55%),
    radial-gradient(900px 520px at 95% 10%, rgba(198,106,47,.20), transparent 52%),
    linear-gradient(180deg, var(--bg0), var(--bg1));
  font-family:"Avenir Next", Avenir, Futura, "Gill Sans", "Trebuchet MS", sans-serif;
  -webkit-font-smoothing:antialiased;
  line-height:1.35;
}
.wrap{max-width:1120px;margin:0 auto;padding:28px 18px 60px}
header{
  padding:18px 18px 14px;
  border:1px solid var(--line);
  border-radius:calc(var(--radius) + 6px);
  background:linear-gradient(180deg, rgba(255,255,255,.74), rgba(255,255,255,.58));
  box-shadow:var(--shadow);
  backdrop-filter:blur(10px);
  position:relative;
  overflow:hidden;
}
header:before{
  content:"";
  position:absolute; inset:-2px;
  background:
    radial-gradient(900px 260px at 8% 0%, rgba(31,122,116,.18), transparent 65%),
    radial-gradient(700px 260px at 98% 0%, rgba(198,106,47,.16), transparent 60%);
  pointer-events:none;
}
.title{
  position:relative;
  display:flex; gap:14px; align-items:flex-end; justify-content:space-between; flex-wrap:wrap;
}
h1{
  margin:0;
  font-family:"Iowan Old Style","Palatino Linotype",Palatino,serif;
  font-weight:700;
  letter-spacing:.2px;
  font-size:28px;
}
.sub{
  margin:6px 0 0;
  color:var(--muted);
  font-size:14px;
}
.meta{
  position:relative;
  display:flex; gap:10px; flex-wrap:wrap;
  margin-top:14px;
}
.pill{
  border:1px solid var(--line);
  border-radius:999px;
  padding:8px 10px;
  background:rgba(255,255,255,.55);
  font-size:13px;
}
.grid{
  display:grid;
  grid-template-columns:1fr;
  gap:14px;
  margin-top:18px;
}
.card{
  border:1px solid var(--line);
  border-radius:var(--radius);
  background:var(--card);
  box-shadow:0 10px 40px rgba(22,24,22,.10);
  backdrop-filter:blur(10px);
  overflow:hidden;
  animation:rise .35s ease-out both;
}
@keyframes rise{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
.card-h{
  padding:14px 16px 10px;
  display:flex; align-items:flex-start; justify-content:space-between; gap:12px; flex-wrap:wrap;
  border-bottom:1px solid var(--line);
  background:linear-gradient(180deg, rgba(255,255,255,.65), rgba(255,255,255,.35));
}
.card-h .when{
  font-weight:700;
  letter-spacing:.2px;
  font-size:16px;
}
.card-h .when small{display:block;color:var(--muted);font-weight:500;font-size:12px;margin-top:3px}
.badges{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.badge{
  display:inline-flex;align-items:center;gap:6px;
  padding:7px 10px;
  border-radius:999px;
  font-size:12px;
  border:1px solid var(--line);
  background:rgba(255,255,255,.55);
}
.badge-ok{border-color:rgba(31,111,59,.25); color:var(--ok)}
.badge-warn{border-color:rgba(160,96,0,.25); color:var(--warn)}
.badge-bad{border-color:rgba(166,27,43,.25); color:var(--bad)}
.body{
  display:grid;
  grid-template-columns:1.3fr .7fr;
  gap:14px;
  padding:14px 16px 16px;
}
.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:14px;background:rgba(255,255,255,.55)}
table{
  width:100%;
  border-collapse:separate;
  border-spacing:0;
  min-width:680px;
  font-size:13px;
}
thead th{
  position:sticky; top:0;
  background:rgba(248,244,232,.92);
  backdrop-filter:blur(8px);
  text-align:left;
  padding:10px 10px;
  border-bottom:1px solid var(--line);
  font-weight:700;
}
tbody td{
  padding:10px 10px;
  border-bottom:1px solid rgba(22,24,22,.08);
  vertical-align:top;
}
tbody tr:nth-child(odd){background:rgba(255,255,255,.35)}
.num{font-family:var(--mono); text-align:right; white-space:nowrap}
.notes{color:var(--muted)}
.row-urgent{background:rgba(166,27,43,.08)!important}
.row-sale{background:rgba(31,111,59,.07)!important}
.prompt{
  border:1px solid var(--line);
  border-radius:14px;
  background:rgba(255,255,255,.55);
  overflow:hidden;
  display:flex;
  flex-direction:column;
  min-height:260px;
}
.prompt-h{
  display:flex;align-items:center;justify-content:space-between;gap:10px;
  padding:10px 10px;
  border-bottom:1px solid var(--line);
}
.prompt-h b{font-size:13px}
textarea{
  width:100%;
  resize:vertical;
  min-height:200px;
  border:0;
  outline:0;
  padding:10px 10px 12px;
  background:transparent;
  color:var(--ink);
  font-family:var(--mono);
  font-size:12px;
  line-height:1.35;
}
.btn{
  appearance:none;
  border:1px solid rgba(31,122,116,.35);
  background:linear-gradient(180deg, rgba(31,122,116,.14), rgba(31,122,116,.06));
  color:var(--ink);
  border-radius:12px;
  padding:8px 10px;
  font-size:12px;
  cursor:pointer;
  transition:transform .08s ease, box-shadow .12s ease, background .12s ease;
}
.btn:hover{box-shadow:0 10px 25px rgba(31,122,116,.12)}
.btn:active{transform:translateY(1px)}
.toast{
  position:fixed;
  right:16px;
  bottom:16px;
  background:rgba(22,24,22,.88);
  color:#fff;
  padding:10px 12px;
  border-radius:12px;
  font-size:12px;
  opacity:0;
  transform:translateY(6px);
  transition:opacity .15s ease, transform .15s ease;
  pointer-events:none;
}
.toast.show{opacity:1;transform:translateY(0)}
.foot{
  margin-top:14px;
  color:var(--muted);
  font-size:12px;
}
@media (max-width: 980px){
  .body{grid-template-columns:1fr}
  table{min-width:620px}
}
""")
    parts.append("  </style>")
    parts.append("</head>")
    parts.append("<body>")
    parts.append('  <div class="wrap">')
    parts.append("    <header>")
    parts.append('      <div class="title">')
    parts.append('        <div>')
    parts.append("          <h1>Coles Order Plan</h1>")
    parts.append(f'          <div class="sub">Generated {html.escape(generated_at)}. Minimal-stock strategy with {ORDERS_PER_WEEK} orders/week.</div>')
    parts.append("        </div>")
    parts.append('        <div class="badges">')
    parts.append(badge(f"{orders_placed} orders", "ok" if orders_placed else "warn"))
    parts.append(badge(f"Total {_safe_money(total_spend)}", "ok"))
    parts.append(badge(f"Delivery {_safe_money(delivery_fees)}", "warn" if delivery_fees else "ok"))
    parts.append("        </div>")
    parts.append("      </div>")
    parts.append('      <div class="meta">')
    parts.append(f'        <div class="pill"><b>Last invoice</b>: {html.escape(_format_date(last_invoice_date))}</div>')
    parts.append(f'        <div class="pill"><b>Start</b>: {html.escape(_format_date(prediction_start))}</div>')
    parts.append(f'        <div class="pill"><b>Horizon end</b>: {html.escape(_format_date(horizon_end))}</div>')
    parts.append(f'        <div class="pill"><b>Min order</b>: {_safe_money(MIN_ORDER_TOTAL)} <span style="color:var(--muted)">+ delivery</span></div>')
    parts.append("      </div>")
    parts.append("    </header>")

    if skipped_orders:
        parts.append(f'<div class="foot">Skipped/merged orders: {len(skipped_orders)} (merged into nearby orders).</div>')

    parts.append('    <div class="grid">')

    for idx, order in enumerate(active_orders, start=1):
        order_date = pd.to_datetime(order.get("date"))
        days_until = (order_date.normalize() - today).days
        urgent = days_until <= 3
        meets = bool(order.get("meets_minimum"))
        items_total = float(order.get("items_total", 0) or 0)
        total_with_delivery = float(order.get("total_with_delivery", 0) or 0)

        if meets:
            status_badge = badge("MEETS MINIMUM", "ok")
        else:
            status_badge = badge("BELOW MINIMUM", "bad")

        when_sub = f"in {days_until} day(s)" if days_until >= 0 else f"{abs(days_until)} day(s) ago"
        if urgent:
            when_sub += " (soon)"

        prompt_id = f"prompt-{idx}"
        prompt_text = _build_reorder_prompt(order)

        parts.append('      <section class="card">')
        parts.append('        <div class="card-h">')
        parts.append(f'          <div class="when">Order {idx}: {html.escape(order_date.strftime("%A, %d %B %Y"))}<small>{html.escape(when_sub)}</small></div>')
        parts.append('          <div class="badges">')
        parts.append(status_badge)
        if urgent:
            parts.append(badge("URGENT", "bad"))
        parts.append(badge(f"Items {_safe_money(items_total)}", "warn" if not meets else "ok"))
        parts.append(badge(f"With delivery {_safe_money(total_with_delivery)}", "ok" if meets else "warn"))
        parts.append("          </div>")
        parts.append("        </div>")

        parts.append('        <div class="body">')
        parts.append('          <div class="table-wrap">')
        parts.append("            <table>")
        parts.append("              <thead><tr>")
        parts.append("                <th style=\"width:54%\">Product</th>")
        parts.append("                <th class=\"num\" style=\"width:10%\">Qty</th>")
        parts.append("                <th class=\"num\" style=\"width:12%\">Unit</th>")
        parts.append("                <th class=\"num\" style=\"width:12%\">Total</th>")
        parts.append("                <th style=\"width:12%\">Notes</th>")
        parts.append("              </tr></thead>")
        parts.append("              <tbody>")

        for item in sorted(order.get("items", []), key=lambda x: -x.get("total_price", 0)):
            raw_name = str(item.get("product", ""))
            product_name = raw_name.lstrip("%").strip()
            qty = item.get("qty", 0)
            unit_price = float(item.get("unit_price", 0) or 0)
            total_price = float(item.get("total_price", 0) or 0)

            notes = []
            if item.get("topped_up"):
                notes.append("top-up")
            elif float(item.get("stock_before", 999)) < 0.5:
                notes.append("restock")

            pstats = product_stats.get(raw_name, product_stats.get(product_name, {})) if product_stats else {}
            on_sale = False
            if pstats.get("has_promos"):
                min_price = float(pstats.get("min_price", unit_price) or unit_price)
                if unit_price <= min_price:
                    notes.append("ON SALE")
                    on_sale = True
                else:
                    notes.append(f"sale@{_safe_money(min_price)}")

            row_class = []
            if item.get("urgent"):
                row_class.append("row-urgent")
            if on_sale:
                row_class.append("row-sale")
            row_class_attr = f' class="{" ".join(row_class)}"' if row_class else ""

            parts.append(f"                <tr{row_class_attr}>")
            parts.append(f"                  <td>{html.escape(product_name)}</td>")
            parts.append(f"                  <td class=\"num\">{html.escape(str(qty))}</td>")
            parts.append(f"                  <td class=\"num\">{html.escape(_safe_money(unit_price))}</td>")
            parts.append(f"                  <td class=\"num\">{html.escape(_safe_money(total_price))}</td>")
            parts.append(f"                  <td class=\"notes\">{html.escape(', '.join(notes))}</td>")
            parts.append("                </tr>")

        parts.append("              </tbody>")
        parts.append("            </table>")
        parts.append("          </div>")

        parts.append('          <aside class="prompt">')
        parts.append('            <div class="prompt-h">')
        parts.append('              <b>Copyable Prompt</b>')
        parts.append(f'              <button class="btn" type="button" onclick="copyPrompt({html.escape(repr(prompt_id))})">Copy</button>')
        parts.append("            </div>")
        parts.append(f'            <textarea id="{html.escape(prompt_id)}" readonly spellcheck="false">{html.escape(prompt_text)}</textarea>')
        parts.append("          </aside>")
        parts.append("        </div>")

        if order.get("notes"):
            notes_joined = " | ".join(str(n) for n in order.get("notes", []))
            parts.append(f'        <div class="foot" style="padding:0 16px 14px">{html.escape(notes_joined)}</div>')

        parts.append("      </section>")

    parts.append("    </div>")

    parts.append('    <div class="foot">')
    parts.append(f'      Report file: <span style="font-family:var(--mono)">{html.escape(output_path)}</span>')
    parts.append("    </div>")

    parts.append('    <div id="toast" class="toast">Copied</div>')
    parts.append("  </div>")
    parts.append("  <script>")
    parts.append("""
function showToast(text){
  const el = document.getElementById('toast');
  el.textContent = text || 'Copied';
  el.classList.add('show');
  window.clearTimeout(showToast._t);
  showToast._t = window.setTimeout(() => el.classList.remove('show'), 1100);
}
async function copyPrompt(id){
  const ta = document.getElementById(id);
  if (!ta) return;
  const text = ta.value;
  try{
    await navigator.clipboard.writeText(text);
    showToast('Copied prompt');
    return;
  }catch(e){}
  try{
    ta.focus();
    ta.select();
    document.execCommand('copy');
    showToast('Copied prompt');
  }catch(e){
    showToast('Copy failed');
  }
}
""")
    parts.append("  </script>")
    parts.append("</body>")
    parts.append("</html>")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))

    print(green(f"Wrote HTML report: {output_path}"))


def write_analyze_html(group_name, group_products, representative, rep_stats, group_df, excluded_rows, orders, promo_info, product_prices, in_stock_dict, stock_date, output_path):
    """Write a standalone HTML analysis report for a single product group."""
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    generated_at = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")

    parts = []
    parts.append("<!doctype html>")
    parts.append('<html lang="en">')
    parts.append("<head>")
    parts.append('  <meta charset="utf-8" />')
    parts.append('  <meta name="viewport" content="width=device-width, initial-scale=1" />')
    parts.append(f"  <title>Analysis: {html.escape(group_name)}</title>")
    parts.append("  <style>")
    parts.append("""
:root{
  --bg0:#fbf4e8;
  --bg1:#e8f2f0;
  --ink:#161816;
  --muted:#4b514b;
  --card:rgba(255,255,255,.74);
  --line:rgba(22,24,22,.12);
  --shadow:0 18px 60px rgba(22,24,22,.12);
  --accent:#1f7a74;
  --accent2:#c66a2f;
  --ok:#1f6f3b;
  --warn:#a06000;
  --bad:#a61b2b;
  --radius:18px;
  --mono:ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
}
*{box-sizing:border-box}
html,body{height:100%}
body{
  margin:0;
  color:var(--ink);
  background:
    radial-gradient(1200px 650px at 12% 6%, rgba(31,122,116,.22), transparent 55%),
    radial-gradient(900px 520px at 95% 10%, rgba(198,106,47,.20), transparent 52%),
    linear-gradient(180deg, var(--bg0), var(--bg1));
  font-family:"Avenir Next", Avenir, Futura, "Gill Sans", "Trebuchet MS", sans-serif;
  -webkit-font-smoothing:antialiased;
  line-height:1.35;
}
.wrap{max-width:900px;margin:0 auto;padding:28px 18px 60px}
header{
  padding:18px 18px 14px;
  border:1px solid var(--line);
  border-radius:calc(var(--radius) + 6px);
  background:linear-gradient(180deg, rgba(255,255,255,.74), rgba(255,255,255,.58));
  box-shadow:var(--shadow);
  backdrop-filter:blur(10px);
}
h1{margin:0;font-family:"Iowan Old Style","Palatino Linotype",Palatino,serif;font-weight:700;font-size:24px}
.sub{margin:6px 0 0;color:var(--muted);font-size:13px}
section{
  margin-top:14px;
  border:1px solid var(--line);
  border-radius:var(--radius);
  background:var(--card);
  box-shadow:0 10px 40px rgba(22,24,22,.10);
  backdrop-filter:blur(10px);
  overflow:hidden;
}
section h2{
  margin:0;padding:12px 16px;
  font-size:15px;
  border-bottom:1px solid var(--line);
  background:linear-gradient(180deg, rgba(255,255,255,.65), rgba(255,255,255,.35));
}
section .body{padding:14px 16px}
table{width:100%;border-collapse:separate;border-spacing:0;font-size:13px}
thead th{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);font-weight:700;background:rgba(248,244,232,.92)}
tbody td{padding:8px 10px;border-bottom:1px solid rgba(22,24,22,.08);vertical-align:top}
tbody tr:nth-child(odd){background:rgba(255,255,255,.35)}
.num{font-family:var(--mono);text-align:right;white-space:nowrap}
.metric{display:inline-block;margin:4px 10px 4px 0;padding:6px 10px;border:1px solid var(--line);border-radius:12px;font-size:13px;background:rgba(255,255,255,.55)}
.metric b{margin-right:4px}
.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}
.foot{margin-top:14px;color:var(--muted);font-size:12px}
""")
    parts.append("  </style>")
    parts.append("</head>")
    parts.append("<body>")
    parts.append('  <div class="wrap">')

    # Header
    parts.append("    <header>")
    parts.append(f"      <h1>Analysis: {html.escape(group_name)}</h1>")
    rep_label = f"Representative: {html.escape(representative)} ({_safe_money(rep_stats['unit_price'])})" if representative and rep_stats else "No representative found"
    parts.append(f'      <div class="sub">{rep_label} &middot; Generated {html.escape(generated_at)}</div>')
    parts.append(f'      <div class="sub">Products: {html.escape(", ".join(group_products))}</div>')
    parts.append("    </header>")

    # Section 1: Raw Order History
    parts.append('    <section><h2>1. Raw Order History</h2><div class="body">')
    if group_df is not None and not group_df.empty:
        sorted_df = group_df.sort_values("ds")
        parts.append('      <table><thead><tr><th>Date</th><th>Product</th><th class="num">Qty</th><th class="num">Price</th></tr></thead><tbody>')
        for _, row in sorted_df.iterrows():
            price = product_prices.get(row["product"], {}).get("price", 0)
            parts.append(f'        <tr><td>{html.escape(row["ds"].strftime("%Y-%m-%d"))}</td><td>{html.escape(str(row["product"]))}</td><td class="num">{row["y"]:.0f}</td><td class="num">{html.escape(_safe_money(price))}</td></tr>')
        parts.append("      </tbody></table>")
        parts.append(f'      <div class="foot">{len(sorted_df)} rows</div>')
    else:
        parts.append("      <p>No order history found.</p>")
    parts.append("    </div></section>")

    # Section 2: Anomalies Excluded
    parts.append('    <section><h2>2. Anomalies Excluded</h2><div class="body">')
    if excluded_rows:
        parts.append('      <table><thead><tr><th>Date</th><th class="num">Qty</th><th class="num">Threshold</th><th class="num">Median</th><th>Reason</th></tr></thead><tbody>')
        for ex in excluded_rows:
            parts.append(f'        <tr><td>{html.escape(ex["date"].strftime("%Y-%m-%d"))}</td><td class="num">{ex["qty"]:.0f}</td><td class="num">{ex["threshold"]:.1f}</td><td class="num">{ex["median"]:.1f}</td><td>Upper outlier</td></tr>')
        parts.append("      </tbody></table>")
    else:
        parts.append('      <p class="ok">None detected</p>')
    parts.append("    </div></section>")

    # Section 3: Consumption Metrics
    parts.append('    <section><h2>3. Consumption Metrics</h2><div class="body">')
    if rep_stats:
        dr = rep_stats["daily_rate"]
        ai = rep_stats["avg_interval"]
        aq = rep_stats["avg_qty_per_order"]
        oc = rep_stats["order_count"]
        wn = rep_stats["weekly_need"]
        parts.append(f'      <span class="metric"><b>Daily rate:</b> {dr:.4f}</span>')
        parts.append(f'      <span class="metric"><b>Weekly need:</b> {wn:.2f}</span>')
        parts.append(f'      <span class="metric"><b>Avg interval:</b> {f"{ai:.1f} days" if ai else "N/A"}</span>')
        parts.append(f'      <span class="metric"><b>Avg qty/order:</b> {aq:.2f}</span>')
        parts.append(f'      <span class="metric"><b>Order count:</b> {oc}</span>')
        parts.append(f'      <span class="metric"><b>Frequent:</b> {"Yes" if rep_stats["frequent"] else "No"}</span>')
    else:
        parts.append("      <p>No metrics available.</p>")
    parts.append("    </div></section>")

    # Section 4: Stock Estimate
    parts.append('    <section><h2>4. Stock Estimate</h2><div class="body">')
    if rep_stats:
        parts.append(f'      <span class="metric"><b>Source:</b> {html.escape(rep_stats["stock_source"])}</span>')
        if stock_date:
            parts.append(f'      <span class="metric"><b>Stock date:</b> {html.escape(stock_date.strftime("%Y-%m-%d"))}</span>')
        parts.append(f'      <span class="metric"><b>Estimated stock:</b> {rep_stats["estimated_stock"]:.1f}</span>')
        dte = rep_stats["days_until_empty"]
        dte_class = "ok" if dte > 7 else ("warn" if dte > 3 else "bad")
        parts.append(f'      <span class="metric"><b>Days until empty:</b> <span class="{dte_class}">{dte:.1f}</span></span>')
    else:
        parts.append("      <p>No stock data available.</p>")
    parts.append("    </div></section>")

    # Section 5: Order Plan
    parts.append('    <section><h2>5. Order Plan</h2><div class="body">')
    order_rows = []
    if representative:
        for idx, order in enumerate(orders):
            if order.get("skipped"):
                continue
            for item in order.get("items", []):
                if item["product"] == representative:
                    order_rows.append((idx, order, item))
    if order_rows:
        parts.append('      <table><thead><tr><th>Order</th><th>Date</th><th class="num">Qty</th><th class="num">Total</th><th>Stock Before</th><th>Notes</th></tr></thead><tbody>')
        for idx, order, item in order_rows:
            date_str = order["date"].strftime("%A, %d %B %Y")
            notes = "URGENT" if item.get("urgent") else ""
            parts.append(f'        <tr><td>#{idx+1}</td><td>{html.escape(date_str)}</td><td class="num">{item["qty"]}</td><td class="num">{html.escape(_safe_money(item["total_price"]))}</td><td>{item.get("stock_before", "?")}</td><td>{html.escape(notes)}</td></tr>')
        parts.append("      </tbody></table>")
    else:
        parts.append('      <p class="warn">Not scheduled in any order</p>')
    parts.append("    </div></section>")

    # Section 6: Promo Patterns
    parts.append('    <section><h2>6. Promo Patterns</h2><div class="body">')
    if rep_stats and rep_stats.get("has_promos"):
        parts.append(f'      <span class="metric"><b>Price range:</b> {_safe_money(rep_stats["min_price"])} - {_safe_money(rep_stats["max_price"])}</span>')
        parts.append(f'      <span class="metric"><b>Avg price:</b> {_safe_money(rep_stats["avg_price"])}</span>')
        parts.append(f'      <span class="metric"><b>Savings:</b> {rep_stats["savings_pct"]:.0f}%</span>')
        best_days = ", ".join(rep_stats.get("best_days", [])) or "N/A"
        best_weeks = ", ".join(str(w) for w in rep_stats.get("best_weeks", [])) or "N/A"
        parts.append(f'      <span class="metric"><b>Best days:</b> {html.escape(best_days)}</span>')
        parts.append(f'      <span class="metric"><b>Best weeks:</b> {html.escape(best_weeks)}</span>')
        parts.append(f'      <span class="metric"><b>Stock-up qty:</b> {rep_stats["promo_stock_up"]}</span>')
    else:
        parts.append('      <p class="warn">No promotional patterns detected</p>')
    parts.append("    </div></section>")

    parts.append('    <div class="foot">')
    parts.append(f'      Report: <span style="font-family:var(--mono)">{html.escape(output_path)}</span>')
    parts.append("    </div>")
    parts.append("  </div>")
    parts.append("</body>")
    parts.append("</html>")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))

    print(green(f"\nWrote analysis HTML report: {output_path}"))


def analyze_product_group(group_name, df_grouped, product_stats, orders, promo_info, product_prices, generic_mappings, in_stock_dict, stock_date, prediction_start, last_invoice_date):
    """Analyze a single generic product group end-to-end."""
    group_products = generic_mappings.get(group_name, [])

    print(cyan(bold(f"\n{'='*80}")))
    print(cyan(bold(f"  ANALYSIS: {group_name}")))
    print(cyan(bold(f"{'='*80}")))
    print(f"Group products: {', '.join(group_products)}")

    # Find representative in product_stats
    representative = None
    rep_stats = None
    for p, s in product_stats.items():
        if s.get("is_group_representative") and s.get("group_name") == group_name:
            representative = p
            rep_stats = s
            break

    if representative:
        print(f"Representative: {representative} ({_safe_money(rep_stats['unit_price'])})")
    else:
        print(yellow("No representative found in product_stats (group may have been filtered out)"))

    # --- Section 1: Raw Order History ---
    print(cyan(bold(f"\n--- 1. RAW ORDER HISTORY ---")))
    group_df = df_grouped[df_grouped["product"].isin(group_products)].copy()
    if group_df.empty:
        print(yellow("  No order history found for this group."))
    else:
        group_df = group_df.sort_values("ds")
        print(f"  {'Date':<14}{'Product':<50}{'Qty':>6}{'Price':>10}")
        print(f"  {'-'*14}{'-'*50}{'-'*6}{'-'*10}")
        for _, row in group_df.iterrows():
            price = product_prices.get(row["product"], {}).get("price", 0)
            print(f"  {row['ds'].strftime('%Y-%m-%d'):<14}{row['product'][:49]:<50}{row['y']:>6.0f}{_safe_money(price):>10}")
        print(f"  Total rows: {len(group_df)}")

    # --- Section 2: Anomalies Excluded ---
    print(cyan(bold(f"\n--- 2. ANOMALIES EXCLUDED ---")))
    oldest_invoice_date = df_grouped["ds"].min()
    group_daily_df = group_df.groupby("ds")["y"].sum().reset_index() if not group_df.empty else pd.DataFrame(columns=["ds", "y"])
    if not group_daily_df.empty:
        _, _, _, _, _, _, _, excluded_rows = calculate_consumption_metrics(group_daily_df, oldest_invoice_date)
    else:
        excluded_rows = []
    if excluded_rows:
        print(f"  {'Date':<14}{'Qty':>6}{'Threshold':>12}{'Median':>10}  Reason")
        print(f"  {'-'*14}{'-'*6}{'-'*12}{'-'*10}  {'-'*14}")
        for ex in excluded_rows:
            print(f"  {ex['date'].strftime('%Y-%m-%d'):<14}{ex['qty']:>6.0f}{ex['threshold']:>12.1f}{ex['median']:>10.1f}  Upper outlier")
    else:
        print(green("  None detected"))

    # --- Section 3: Consumption Metrics ---
    print(cyan(bold(f"\n--- 3. CONSUMPTION METRICS ---")))
    if rep_stats:
        dr = rep_stats["daily_rate"]
        ai = rep_stats["avg_interval"]
        aq = rep_stats["avg_qty_per_order"]
        oc = rep_stats["order_count"]
        wn = rep_stats["weekly_need"]
        print(f"  Daily rate: {dr:.4f}")
        print(f"  Weekly need: {wn:.2f}")
        print(f"  Avg interval: {f'{ai:.1f} days' if ai else 'N/A'}")
        print(f"  Avg qty/order: {aq:.2f}")
        print(f"  Order count: {oc}")
        print(f"  Frequent: {rep_stats['frequent']}")
    else:
        print(yellow("  No consumption metrics (no representative found)"))

    # --- Section 4: Stock Estimate ---
    print(cyan(bold(f"\n--- 4. STOCK ESTIMATE ---")))
    if rep_stats:
        print(f"  Source: {rep_stats['stock_source']}")
        if stock_date:
            print(f"  Stock date: {stock_date.strftime('%Y-%m-%d')}")
        # Show actual stock values from in-stock
        for p in group_products:
            qty = match_product_to_stock(p, in_stock_dict)
            if qty is not None:
                print(f"  In-stock match: {p} = {qty}")
        print(f"  Estimated current stock: {rep_stats['estimated_stock']:.1f}")
        print(f"  Days until empty: {rep_stats['days_until_empty']:.1f}")
    else:
        print(yellow("  No stock estimate (no representative found)"))

    # --- Section 5: Order Plan ---
    print(cyan(bold(f"\n--- 5. ORDER PLAN ---")))
    found_in_orders = False
    for idx, order in enumerate(orders):
        if order.get("skipped"):
            continue
        for item in order.get("items", []):
            if item["product"] == representative:
                found_in_orders = True
                date_str = order["date"].strftime("%Y-%m-%d (%A)")
                urgent_tag = " [URGENT]" if item.get("urgent") else ""
                print(f"  Order #{idx+1} ({date_str}): {item['qty']}x {representative} = {_safe_money(item['total_price'])}{urgent_tag}")
                print(f"    Stock before: {item.get('stock_before', '?')}, Need until next: {item.get('need_until_next', '?')}")
    if not found_in_orders:
        print(yellow("  Not scheduled in any order"))

    # --- Section 6: Promo Patterns ---
    print(cyan(bold(f"\n--- 6. PROMO PATTERNS ---")))
    if rep_stats and rep_stats.get("has_promos"):
        print(f"  Has promos: Yes")
        print(f"  Price range: {_safe_money(rep_stats['min_price'])} - {_safe_money(rep_stats['max_price'])} (avg {_safe_money(rep_stats['avg_price'])})")
        print(f"  Savings: {rep_stats['savings_pct']:.0f}%")
        print(f"  Best days: {', '.join(rep_stats.get('best_days', [])) or 'N/A'}")
        print(f"  Best weeks: {', '.join(str(w) for w in rep_stats.get('best_weeks', [])) or 'N/A'}")
        print(f"  Promo stock-up qty: {rep_stats['promo_stock_up']}")
    elif rep_stats:
        print(yellow("  No promotional patterns detected"))
    else:
        print(yellow("  No promo data (no representative found)"))

    # Write HTML analysis report
    html_path = os.path.join(OUTPUT_DIR, f"analyze-{group_name.lower().replace(' ', '-')}.html")
    write_analyze_html(group_name, group_products, representative, rep_stats, group_df, excluded_rows, orders, promo_info, product_prices, in_stock_dict, stock_date, html_path)


def predict_two_dollar_delivery_orders(analyze_group=None):
    # DEBUG: Products to trace
    DEBUG_PRODUCTS = [
        "%Swisse Ultivite Women''s Multivitamin With Key Nut",
        "Foaming",
        "Handwash"
    ]
    
    df_grouped, product_prices, last_invoice_date, price_history = load_grouped_orders()
    if df_grouped is None:
        print(red("No data found to predict."))
        return

    print(green(f"Loaded {len(df_grouped)} grouped records across {df_grouped['product'].nunique()} products."))
    
    # DEBUG: Check if target products are in the data
    print(cyan(f"\n{'='*80}"))
    print(cyan(bold("DEBUG: Searching for target products in data...")))
    print(cyan(f"{'='*80}"))
    all_products = df_grouped["product"].unique()
    for debug_prod in DEBUG_PRODUCTS:
        matches = [p for p in all_products if debug_prod.lower() in p.lower() or p.lower() in debug_prod.lower()]
        if matches:
            print(green(f"✓ Found matches for '{debug_prod}':"))
            for match in matches:
                print(f"  - {match}")
        else:
            print(red(f"✗ No matches found for '{debug_prod}'"))

    if last_invoice_date is None:
        print(red("Could not determine last invoice date."))
        return

    # Load in-stock data
    in_stock_dict, stock_date = load_in_stock()

    # Load dont-order list and generic products
    dont_order = load_dont_order()
    generic_mappings = load_generic_products()
    print(green(f"Loaded {len(dont_order)} items in dont-order list"))
    print(green(f"Loaded {len(generic_mappings)} generic product groups"))

    # Analyze price patterns to detect promotions
    promo_info = analyze_price_patterns(price_history)
    promo_count = sum(1 for p in promo_info.values() if p.get("has_promos", False))
    print(green(f"Analyzed price history: {len(price_history)} products, {promo_count} with promotional patterns."))

    # Plan for one month from the last invoice date
    horizon_end = last_invoice_date + timedelta(days=PREDICTION_WINDOW_DAYS)
    today = pd.Timestamp.now().normalize()
    prediction_start = max(today, last_invoice_date + timedelta(days=1))
    if prediction_start > horizon_end:
        print(f"Last invoice is over 3 weeks old; no forward window to plan.")
        return

    product_stats = compute_product_stats(df_grouped, product_prices, last_invoice_date, prediction_start, promo_info, in_stock_dict, stock_date, generic_mappings, dont_order)
    if not product_stats:
        print(red("No products with measurable demand."))
        return
    
    # DEBUG: Check if target products made it into product_stats
    print(cyan(f"\n{'='*80}"))
    print(cyan(bold("DEBUG: Checking if target products are in product_stats...")))
    print(cyan(f"{'='*80}"))
    for debug_prod in DEBUG_PRODUCTS:
        matches = [p for p in product_stats.keys() if debug_prod.lower() in p.lower() or p.lower() in debug_prod.lower()]
        if matches:
            for match in matches:
                stats = product_stats[match]
                print(green(f"✓ '{match}' is in product_stats:"))
                print(f"  Daily rate: {stats['daily_rate']:.3f}")
                print(f"  Weekly need: {stats['weekly_need']:.3f}")
                print(f"  Estimated stock: {stats['estimated_stock']:.1f}")
                print(f"  Days until empty: {stats['days_until_empty']:.1f}")
                print(f"  Unit price: ${stats['unit_price']:.2f}")
                print(f"  Frequent: {stats['frequent']}")
        else:
            print(red(f"✗ No matches for '{debug_prod}' in product_stats - product was filtered during compute_product_stats"))

    # Filter out products in dont-order list
    skipped_blocked = 0
    filtered_stats = {}
    for product, stats in product_stats.items():
        if is_product_blocked(product, dont_order, generic_mappings):
            skipped_blocked += 1
            # DEBUG: Check if it's one of our target products
            for debug_prod in DEBUG_PRODUCTS:
                if debug_prod.lower() in product.lower() or product.lower() in debug_prod.lower():
                    print(red(f"DEBUG: '{product}' was BLOCKED by dont-order list"))
        else:
            filtered_stats[product] = stats
    product_stats = filtered_stats
    if skipped_blocked > 0:
        print(yellow(f"Skipped {skipped_blocked} products (in dont-order list)"))
    
    # DEBUG: Final check after dont-order filtering
    print(cyan(f"\n{'='*80}"))
    print(cyan(bold("DEBUG: Final check after dont-order filtering...")))
    print(cyan(f"{'='*80}"))
    for debug_prod in DEBUG_PRODUCTS:
        matches = [p for p in product_stats.keys() if debug_prod.lower() in p.lower() or p.lower() in debug_prod.lower()]
        if matches:
            for match in matches:
                print(green(f"✓ '{match}' survived dont-order filtering"))
        else:
            print(red(f"✗ '{debug_prod}' not in final product_stats"))

    order_dates = generate_order_dates(prediction_start, horizon_end)
    if not order_dates:
        print(yellow("No order dates fall within the one-month planning window."))
        return
    orders = build_minimal_orders(product_stats, order_dates, prediction_start)
    
    # DEBUG: Check first order before consolidation
    if orders:
        first_order_items = len(orders[0]["items"])
        urgent_items = [item for item in orders[0]["items"] if item.get("urgent")]
        print(cyan(f"\nDEBUG: First order has {first_order_items} items, {len(urgent_items)} urgent"))
    
    enforce_minimums(orders, product_stats)

    # Remove duplicate products from consecutive orders
    consolidate_duplicate_products(orders, product_stats)

    consolidate_small_orders(orders)

    # Recalculate totals after consolidation
    for order in orders:
        if not order.get("skipped"):
            order["items_total"] = sum(item["total_price"] for item in order["items"])
            order["total_with_delivery"] = order["items_total"] + DELIVERY_FEE if order["items_total"] > 0 else 0
            order["meets_minimum"] = order["items_total"] >= MIN_ORDER_TOTAL

    print_weekly_plan(orders, product_stats, last_invoice_date, prediction_start, horizon_end)
    report_path = os.path.join(OUTPUT_DIR, "two-dollar-delivery-order-plan.html")
    write_html_report(orders, product_stats, last_invoice_date, prediction_start, horizon_end, report_path)

    # Product group analysis (if requested)
    if analyze_group:
        # Resolve group name case-insensitively
        group_name = None
        for key in generic_mappings:
            if key.lower() == analyze_group.lower():
                group_name = key
                break
        if group_name is None:
            print(red(f"\nError: No generic product group matching '{analyze_group}'."))
            print(f"Available groups:")
            for key in sorted(generic_mappings.keys()):
                print(f"  - {key}")
            return
        analyze_product_group(
            group_name=group_name,
            df_grouped=df_grouped,
            product_stats=product_stats,
            orders=orders,
            promo_info=promo_info,
            product_prices=product_prices,
            generic_mappings=generic_mappings,
            in_stock_dict=in_stock_dict,
            stock_date=stock_date,
            prediction_start=prediction_start,
            last_invoice_date=last_invoice_date,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Predict Coles two-dollar delivery orders")
    parser.add_argument("--analyze", type=str, default=None,
                        help="Analyze a specific generic product group (case-insensitive key from generic-products.json)")
    args = parser.parse_args()
    predict_two_dollar_delivery_orders(analyze_group=args.analyze)
