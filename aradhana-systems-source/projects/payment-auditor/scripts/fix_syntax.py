import re

filepath = r"C:\Users\kaila\aradhana-payment-auditor\aradhana-payment-auditor\backend\review_api.py"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Fix indentation of serve_spa
content = content.replace('@app.get("/{full_path:path}")\n    async def serve_spa', '@app.get("/{full_path:path}")\nasync def serve_spa')

# Find the start of the OLD endpoints at the bottom of the file
# They are right after `if not integrity: logger.critical(...)` and before the end of file
old_endpoints_pattern = r'@app\.get\("/api/dashboard/today-bills"\).*'
# Since we inserted the new ones earlier, we want to remove the ones at the VERY END.
# Let's just find the SECOND occurrence of @app.get("/api/dashboard/today-bills") and slice it off.
parts = content.split('@app.get("/api/dashboard/today-bills")')
if len(parts) > 2:
    # Reassemble up to the second occurrence
    content = parts[0] + '@app.get("/api/dashboard/today-bills")' + parts[1]

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("Fixed syntax and removed duplicate")
