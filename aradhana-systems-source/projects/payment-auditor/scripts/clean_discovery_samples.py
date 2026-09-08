import json
import re
import os

def strip_html(html):
    if not html: return ""
    # Remove script and style elements
    clean = re.sub(r'<(script|style).*?>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
    # Remove remaining tags
    clean = re.sub(r'<.*?>', ' ', clean)
    # Normalize whitespace
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean

def dump_cleaned_samples():
    path = r"C:\Aradhana\BankImports\icici_format_discovery.json"
    if not os.path.exists(path):
        print("Discovery file not found.")
        return

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    print("CLEANED BODY SAMPLES:")
    print("="*50)
    for entry in data["data"]:
        print(f"SUBJECT: {entry['subject']}")
        print(f"CLEANED TEXT: {strip_html(entry['body_sample'])}")
        print("-" * 30)

if __name__ == "__main__":
    dump_cleaned_samples()
