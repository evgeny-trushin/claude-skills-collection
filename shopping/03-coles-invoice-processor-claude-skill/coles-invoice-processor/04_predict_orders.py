import json
import pandas as pd
from prophet import Prophet
import os
import logging
from datetime import timedelta, datetime
import math

# Suppress Prophet logging
logging.getLogger('cmdstanpy').setLevel(logging.ERROR)
logging.getLogger('prophet').setLevel(logging.ERROR)

# Forecast horizon in days (5 months ~ 150 days)
FORECAST_DAYS = 150
OUTPUT_DIR = 'output_extracted'

def predict_orders():
    data_file = os.path.join(OUTPUT_DIR, 'extracted_data.json')
    if not os.path.exists(data_file):
        print(f"Error: {data_file} not found. Please run extraction first.")
        return

    with open(data_file, 'r') as f:
        data = json.load(f)

    # Flatten data and get prices
    rows = []
    product_prices = {} # {product: {'price': float, 'date': datetime}}

    for invoice in data:
        date_str = invoice.get('invoice_date')
        if not date_str:
            continue
            
        try:
            date = pd.to_datetime(date_str, format='%d %B %Y')
        except:
            try:
                date = pd.to_datetime(date_str)
            except:
                continue

        for category in invoice.get('categories', []):
            for item in category.get('items', []):
                product = item.get('product')
                try:
                    quantity = float(item.get('ordered', 0))
                except ValueError:
                    quantity = 0
                
                # Extract price
                try:
                    price_str = item.get('unit_price', '0').replace('$', '').replace(',', '')
                    price = float(price_str)
                    
                    # Store latest price
                    if product not in product_prices or date > product_prices[product]['date']:
                        product_prices[product] = {'price': price, 'date': date}
                except:
                    pass

                if product and quantity > 0:
                    rows.append({
                        'ds': date,
                        'product': product,
                        'y': quantity
                    })

    df = pd.DataFrame(rows)
    
    if df.empty:
        print("No data found to predict.")
        return

    print(f"Loaded {len(df)} records.")
    
    # Group by product and date
    df_grouped = df.groupby(['product', 'ds']).sum().reset_index()

    products = df_grouped['product'].unique()
    print(f"Found {len(products)} unique products.")

    # All predictions (multiple per product if interval is short)
    predictions = []
    
    # Today's date for forecast window
    today = pd.Timestamp.now().normalize()
    forecast_end = today + timedelta(days=FORECAST_DAYS)

    for product in products:
        product_df = df_grouped[df_grouped['product'] == product].copy()
        product_df = product_df.sort_values('ds')
        
        if len(product_df) < 2:
            continue

        # Calculate average interval
        product_df['interval'] = product_df['ds'].diff().dt.days
        avg_interval = product_df['interval'].mean()
        
        if pd.isna(avg_interval) or avg_interval <= 0:
            continue
        
        interval_days = round(avg_interval)
        if interval_days < 1:
            interval_days = 1
            
        last_date = product_df['ds'].max()
        
        # Calculate average quantity from history
        avg_qty = product_df['y'].mean()
        rounded_qty = max(1, round(avg_qty))
        
        unit_price = product_prices.get(product, {}).get('price', 0.0)
        
        # Generate recurring orders within the forecast horizon
        # Start from today, not from last_date
        next_order_date = last_date + timedelta(days=interval_days)
        
        # Skip past dates - only predict future orders
        while next_order_date < today:
            next_order_date = next_order_date + timedelta(days=interval_days)
        
        while next_order_date <= forecast_end:
            total_price = rounded_qty * unit_price
            
            predictions.append({
                'product': product,
                'next_order_date': next_order_date,
                'predicted_qty': rounded_qty,
                'unit_price': unit_price,
                'total_price': total_price,
                'interval': interval_days
            })
            
            # Schedule next recurrence
            next_order_date = next_order_date + timedelta(days=interval_days)

    # Sort by next order date
    predictions.sort(key=lambda x: x['next_order_date'])

    # Group orders (+- 3 days)
    bulk_orders = []
    current_group = []
    group_start_date = None

    for p in predictions:
        if not group_start_date:
            group_start_date = p['next_order_date']
            current_group.append(p)
        else:
            # Check if within 3 days of the group start date
            if (p['next_order_date'] - group_start_date).days <= 3:
                current_group.append(p)
            else:
                bulk_orders.append(current_group)
                current_group = [p]
                group_start_date = p['next_order_date']
    
    if current_group:
        bulk_orders.append(current_group)

    # Merge small orders (< $50) with adjacent orders within 6 days
    MIN_ORDER = 50
    merged_orders = []
    i = 0
    while i < len(bulk_orders):
        current = bulk_orders[i]
        current_total = sum(item['total_price'] for item in current)
        current_date = current[0]['next_order_date']
        
        # If order is below minimum, try to merge with next order
        if current_total < MIN_ORDER and i + 1 < len(bulk_orders):
            next_order = bulk_orders[i + 1]
            next_date = next_order[0]['next_order_date']
            
            # Merge if next order is within 6 days
            if (next_date - current_date).days <= 6:
                # Combine items into the next order
                bulk_orders[i + 1] = current + next_order
                i += 1
                continue
            # Otherwise, try to merge with previous order if within 6 days
            elif merged_orders:
                prev_date = merged_orders[-1][0]['next_order_date']
                if (current_date - prev_date).days <= 6:
                    merged_orders[-1] = merged_orders[-1] + current
                    i += 1
                    continue
        
        merged_orders.append(current)
        i += 1
    
    bulk_orders = merged_orders

    print(f"\n--- Predicted Bulk Orders for Next {FORECAST_DAYS} Days (Min ${MIN_ORDER}, Grouped by 3-6 days) ---")
    
    monthly_budget = {}

    for i, order_group in enumerate(bulk_orders):
        if not order_group: continue
        
        # Determine group date (use the first date in the group)
        group_date = order_group[0]['next_order_date']
        group_total = sum(item['total_price'] for item in order_group)
        
        # Add to monthly budget
        month_key = group_date.strftime('%Y-%B')
        monthly_budget[month_key] = monthly_budget.get(month_key, 0) + group_total

        print(f"\nOrder #{i+1} - Approx Date: {group_date.strftime('%Y-%m-%d')} - Total Est. Cost: ${group_total:.2f}")
        print(f"{'Product':<50} | {'Qty':<5} | {'Unit $':<8} | {'Total $'}")
        print("-" * 80)
        for item in order_group:
            print(f"{item['product'][:47]+'...':<50} | {item['predicted_qty']:<5} | ${item['unit_price']:<7.2f} | ${item['total_price']:.2f}")

    print("\n--- Estimated Monthly Budget ---")
    # Sort by actual date (YYYY-MM format) not alphabetically
    def month_sort_key(item):
        from datetime import datetime
        month_str = item[0]  # e.g. '2026-January'
        return datetime.strptime(month_str, '%Y-%B')
    
    for month, budget in sorted(monthly_budget.items(), key=month_sort_key):
        print(f"{month}: ${budget:.2f}")

if __name__ == "__main__":
    predict_orders()
