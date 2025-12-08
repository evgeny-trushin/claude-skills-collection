import os
import pymupdf4llm

INPUT_DIR = 'input_invoices'

def convert_pdfs_to_markdown():
    # Get all files in the input directory
    files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith('.pdf')]
    
    if not files:
        print("No PDF files found in the current directory.")
        return

    print(f"Found {len(files)} PDF files. Starting conversion...")

    for pdf_file in files:
        try:
            md_filename = os.path.splitext(pdf_file)[0] + ".md"
            pdf_path = os.path.join(INPUT_DIR, pdf_file)
            md_path = os.path.join(INPUT_DIR, md_filename)
            print(f"Converting '{pdf_file}' to '{md_filename}'...")
            
            # Convert PDF to Markdown
            md_text = pymupdf4llm.to_markdown(pdf_path)
            
            # Write to file
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(md_text)
                
            print(f"Successfully converted '{pdf_file}'")
        except Exception as e:
            print(f"Failed to convert '{pdf_file}': {e}")

if __name__ == "__main__":
    convert_pdfs_to_markdown()
