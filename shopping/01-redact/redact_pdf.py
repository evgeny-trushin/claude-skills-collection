import os
import json
import re
import fitz  # PyMuPDF

INPUT_DIR = 'input_invoices'
OUTPUT_DIR = 'input_invoices_redacted'

# Additional patterns to always redact (payment info, store details, etc.)
# Use patterns instead of hardcoded values to avoid embedding exact details.
ADDITIONAL_REDACT_PATTERNS = [
    r'\bStore\s*[:#-]?\s*\d{4,5}\b',             # Store numbers like "Store: 12345"
    r'\b\d{2}\s?\d{3}\s?\d{3}\s?\d{3}\b',        # ABN-style 11 digit numbers
    r'\bMASTERCARD\b',                           # Payment method labels
    r'\b1[38]00\s?\d{3}\s?\d{3}\b',              # 1300/1800 style phone numbers
    r'\b[\w\.-]+@(?:[\w-]+\.)+[\w-]{2,}\b',      # Email addresses
]

# Regex patterns for dynamic content to redact
REDACT_PATTERNS = [
    r'2\*+',                 # Flybuys card like "0000******"
    r'\b2\d{2,}\*{2,}\d*\b',  # Flybuys numbers with leading digits then masks like "000*****"
    r'ending in \d{4}',        # "ending in 0000" patterns
    r'\*{4,}\d{4}',            # Masked card numbers like *****0000
    r'AUTH \d+',               # Auth codes like "AUTH 0000"
    r'\S+@gmail\.com',         # Gmail addresses
    r'U \d+ \d+ [A-Z]+ [A-Z]+, [A-Z]+',
    r'\d+ [A-Z]+ [A-Z]+, [A-Z]+',      
    r'^\d{4}$',                
    r'\d{1,2}:\d{2}:\d{2}',    # Time format HH:MM:SS like "12:53:04"
    r'\d{1,2}:\d{2}[ap]m',     # Time format H:MMam/pm like "11:57am"
]

def redact_pdfs():
    mapping_file = 'obfuscate.online.json'
    
    if not os.path.exists(mapping_file):
        print(f"Error: {mapping_file} not found.")
        return

    try:
        with open(mapping_file, 'r', encoding='utf-8') as f:
            mapping = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        return

    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    pdf_files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith('.pdf')]
    
    if not pdf_files:
        print("No PDF files found to redact.")
        return

    print(f"Found {len(pdf_files)} PDF files. Starting redaction...")

    # Sort keys by length descending to avoid partial replacements
    redact_terms = [key for key in mapping.keys() if not key.startswith("_")]
    redact_terms = sorted(redact_terms, key=len, reverse=True)

    for pdf_file in pdf_files:
        try:
            pdf_path = os.path.join(INPUT_DIR, pdf_file)
            
            # Redact filename: ea##########_######.pdf -> ea[REDACTED]_######.pdf
            redacted_filename = pdf_file
            filename_match = re.match(r'(ea)\d+(_\d+\.pdf)', pdf_file, re.IGNORECASE)
            if filename_match:
                redacted_filename = filename_match.group(1) + "[REDACTED]" + filename_match.group(2)
            
            output_path = os.path.join(OUTPUT_DIR, redacted_filename)
            
            print(f"Redacting '{pdf_file}' -> '{redacted_filename}'...")
            
            doc = fitz.open(pdf_path)
            redaction_count = 0
            
            for page in doc:
                # Search and redact each term from the mapping
                for term in redact_terms:
                    text_instances = page.search_for(term)
                    for inst in text_instances:
                        # Add redaction annotation (black box)
                        page.add_redact_annot(inst, fill=(0, 0, 0))
                        redaction_count += 1
                
                # Get full page text for regex matching
                page_text = page.get_text()
                
                # Search for regex patterns (including additional always-redact patterns) and redact matches
                for pattern in ADDITIONAL_REDACT_PATTERNS + REDACT_PATTERNS:
                    for match in re.finditer(pattern, page_text, flags=re.IGNORECASE):
                        match_text = match.group()
                        text_instances = page.search_for(match_text)
                        for inst in text_instances:
                            page.add_redact_annot(inst, fill=(0, 0, 0))
                            redaction_count += 1
                
                # Also redact invoice numbers (pattern: # followed by digits after "Invoice number")
                # Search for text containing invoice number pattern
                text_dict = page.get_text("dict")
                in_delivery_section = False
                delivery_lines_to_redact = 0
                
                for block in text_dict.get("blocks", []):
                    if block.get("type") == 0:  # Text block
                        for line in block.get("lines", []):
                            for span in line.get("spans", []):
                                text = span.get("text", "").strip()
                                bbox = fitz.Rect(span["bbox"])
                                
                                # Look for invoice number patterns like "#123456789"
                                if text.startswith("#") and len(text) > 1 and text[1:].replace(" ", "").isdigit():
                                    page.add_redact_annot(bbox, fill=(0, 0, 0))
                                    redaction_count += 1
                                
                                # Track delivery section for address redaction
                                if text == "Delivery":
                                    in_delivery_section = True
                                    delivery_lines_to_redact = 3  # Redact next 3 text items after "Delivery"
                                elif in_delivery_section and delivery_lines_to_redact > 0:
                                    if text and text != "When" and not text.startswith("Thursday") and not text.startswith("Monday") and not text.startswith("Tuesday") and not text.startswith("Wednesday") and not text.startswith("Friday") and not text.startswith("Saturday") and not text.startswith("Sunday"):
                                        page.add_redact_annot(bbox, fill=(0, 0, 0))
                                        redaction_count += 1
                                        delivery_lines_to_redact -= 1
                                    if text == "When":
                                        in_delivery_section = False
                
                # Apply all redactions on this page
                page.apply_redactions()
            
            # Save the redacted PDF
            doc.save(output_path)
            doc.close()
            
            print(f"Saved redacted PDF to '{output_path}' ({redaction_count} redactions)")
            
        except Exception as e:
            print(f"Error processing '{pdf_file}': {e}")

    print(f"\nRedaction complete. Files saved to {OUTPUT_DIR}/")

if __name__ == "__main__":
    redact_pdfs()
