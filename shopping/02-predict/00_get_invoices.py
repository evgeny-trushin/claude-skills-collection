#!/usr/bin/env python3
import json
from datetime import datetime

# Read extracted_data.json
with open('output_extracted/extracted_data.json', 'r') as f:
    data = json.load(f)

# Extract all dates and find the latest
dates = []
for invoice in data:
    if invoice.get('invoice_date'):
        try:
            # Parse dates like "17 December 2025"
            date_obj = datetime.strptime(invoice['invoice_date'], '%d %B %Y')
            dates.append(date_obj)
        except ValueError:
            pass

if dates:
    latest_date = max(dates)
    formatted_date = latest_date.strftime('%d %B %Y')

    print(f"\nLatest invoice date: {formatted_date}\n")
    print("=" * 80)
    print("INSTRUCTIONS:")
    print("=" * 80)
    print(f"""
Open each invoice at
coles.com.au/account/orders?status=past
after this date {formatted_date}
in a separate tab for me to review.
Press [View Orders],
then open [Download Invoice]
in a separate tab.
""")
    print("=" * 80)
else:
    print("No valid dates found in extracted_data.json")
