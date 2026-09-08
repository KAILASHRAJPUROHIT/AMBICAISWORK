import re

filepath = r"C:\Users\kaila\aradhana-payment-auditor\aradhana-payment-auditor\frontend\src\pages\DashboardPage.tsx"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Remove unused state variables
content = re.sub(r'const \[showFullPipeline, setShowFullPipeline\] = useState\(false\);\n', '', content)
content = re.sub(r'const \[expandedFeedDates, setExpandedFeedDates\] = useState<Set<string>>\(new Set\(\)\);\n', '', content)

# Remove unused functions
content = re.sub(r'const openPDF = async .*?};\n\n', '', content, flags=re.DOTALL)
content = re.sub(r'const groupedFeed = .*?toggleFeedDate.*?\};\n\n', '', content, flags=re.DOTALL)
content = re.sub(r'const delayInfo = .*?};\n\n', '', content, flags=re.DOTALL)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("DashboardPage.tsx unused code removed")
