import os
import re
import json

INPUT_DIR = 'input_invoices'
OUTPUT_DIR = 'output_extracted'

def extract_data_from_md():
    # Ensure output directory exists so file writes don't fail
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    md_files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith('.md')]
    extracted_data = []

    for md_file in md_files:
        print(f"Processing {md_file}...")
        try:
            md_path = os.path.join(INPUT_DIR, md_file)
            with open(md_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            print(f"Error reading {md_file}: {e}")
            continue

        # Redact filename: ea12345_67890.md -> ea[REDACTED]_67890.md
        redacted_filename = md_file
        filename_match = re.match(r'(ea)\d+(_\d+\.md)', md_file, re.IGNORECASE)
        if filename_match:
            redacted_filename = filename_match.group(1) + "[REDACTED]" + filename_match.group(2)

        invoice_data = {
            "filename": redacted_filename,
            "invoice_number": None,
            "invoice_date": None,
            "invoice_time": None,
            "categories": []
        }

        # Extract Invoice Number
        inv_num_match = re.search(r'\*\*Invoice number:\*\* #?(\[REDACTED\]|\d+)?', content)
        if inv_num_match and inv_num_match.group(1):
            invoice_data["invoice_number"] = inv_num_match.group(1)

        # Extract Invoice Date and Time (time may be redacted/empty)
        date_match = re.search(r'\*\*Invoice date:\*\* (\d+ \w+ \d{4})', content)
        if date_match:
            invoice_data["invoice_date"] = date_match.group(1)
        
        time_match = re.search(r'\*\*Invoice time:\*\* (\d+:\d+:\d+)', content)
        if time_match:
            invoice_data["invoice_time"] = time_match.group(1)

        lines = content.split('\n')
        
        current_category = None
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Detect Category Header
            if "**Product** **Ordered** **Picked** **Unit Price** **Total charged**" in line:
                # Look backwards for the category name
                j = i - 1
                while j >= 0:
                    prev_line = lines[j].strip()
                    # Category is usually **Name**
                    if prev_line.startswith("**") and prev_line.endswith("**") and "Invoice" not in prev_line and "Page" not in prev_line and "Payment" not in prev_line and "Flybuys" not in prev_line:
                        current_category = prev_line.strip('*')
                        # Check if category already exists (e.g. if split across pages)
                        cat_obj = next((c for c in invoice_data["categories"] if c["name"] == current_category), None)
                        if not cat_obj:
                            cat_obj = {"name": current_category, "items": []}
                            invoice_data["categories"].append(cat_obj)
                        break
                    if prev_line and not prev_line.startswith("**"): 
                         # If we hit a non-bold line, maybe we missed the category or it's not there
                         break
                    j -= 1
                i += 1
                continue

            # Parse Items
            if current_category:
                if line.startswith('['):
                    if '](' in line:
                        try:
                            parts = line.split('](', 1)
                            name = parts[0][1:]
                            rest = parts[1]
                            
                            if ')' in rest:
                                link_parts = rest.split(')', 1)
                                link = link_parts[0]
                                stats_str = link_parts[1].strip()
                                
                                # Extract weight/quantity from name
                                weight = None
                                weight_match = re.search(r'(?i)((?:approx\.?\s*)?\d+(?:\.\d+)?\s*(?:g|kg|ml|l|litre|liter|m|metre|meter|pack|each|pk))\s*$', name)
                                if weight_match:
                                    weight = weight_match.group(1)

                                # Handle multi-line stats
                                if not stats_str:
                                    k = i + 1
                                    while k < len(lines):
                                        next_line = lines[k].strip()
                                        if next_line:
                                            stats_str = next_line
                                            i = k # Advance main loop
                                            break
                                        k += 1
                                
                                # Parse stats: Ordered Picked UnitPrice Total
                                # Find prices starting with $
                                stats_tokens = stats_str.split()
                                price_indices = [idx for idx, token in enumerate(stats_tokens) if token.startswith('$')]
                                
                                if len(price_indices) >= 2:
                                    unit_price_idx = price_indices[-2]
                                    total_price_idx = price_indices[-1]
                                    
                                    unit_price = stats_tokens[unit_price_idx]
                                    total_price = stats_tokens[total_price_idx]
                                    
                                    # Ordered is usually first
                                    ordered = stats_tokens[0]
                                    
                                    # Picked is everything between ordered and unit price
                                    # Usually just one token, but let's be safe
                                    picked_tokens = stats_tokens[1:unit_price_idx]
                                    picked = " ".join(picked_tokens)
                                    
                                    item = {
                                        "product": name,
                                        "weight": weight,
                                        "link": link,
                                        "ordered": ordered,
                                        "picked": picked,
                                        "unit_price": unit_price,
                                        "total_price": total_price
                                    }
                                    
                                    cat_obj = next((c for c in invoice_data["categories"] if c["name"] == current_category), None)
                                    if cat_obj:
                                        cat_obj["items"].append(item)
                        except Exception as e:
                            print(f"Error parsing line in {md_file}: {line}. Error: {e}")

            i += 1
            
        extracted_data.append(invoice_data)

    output_file = os.path.join(OUTPUT_DIR, 'extracted_data.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(extracted_data, f, indent=2)
    print(f"Extraction complete. Saved to {output_file}")

if __name__ == "__main__":
    extract_data_from_md()
