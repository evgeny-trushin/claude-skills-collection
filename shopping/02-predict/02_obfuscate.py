import os
import json
import re

INPUT_DIR = 'input_invoices'

def obfuscate_markdown_files():
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

    md_files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith('.md')]
    
    if not md_files:
        print("No Markdown files found to obfuscate.")
        return

    print(f"Found {len(md_files)} Markdown files. Starting obfuscation...")

    for md_file in md_files:
        try:
            md_path = os.path.join(INPUT_DIR, md_file)
            print(f"Obfuscating '{md_file}'...")
            with open(md_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            original_content = content
            # Sort keys by length descending to avoid partial replacements (e.g. replacing "cat" inside "caterpillar" before "caterpillar")
            sorted_keys = sorted(mapping.keys(), key=len, reverse=True)
            
            for key in sorted_keys:
                if key.startswith("_"): continue # Skip comments
                value = mapping[key]
                content = content.replace(key, value)
            
            # Redact Invoice Number
            content = re.sub(r'(\*\*Invoice number:\*\* #)\d+', r'\1[REDACTED]', content)
            
            if content != original_content:
                with open(md_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"Updated '{md_file}'")
            else:
                print(f"No changes needed for '{md_file}'")
                
        except Exception as e:
            print(f"Failed to obfuscate '{md_file}': {e}")

if __name__ == "__main__":
    obfuscate_markdown_files()
