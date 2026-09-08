import re

filepath = r"C:\Users\kaila\aradhana-payment-auditor\aradhana-payment-auditor\frontend\src\pages\DashboardPage.tsx"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Remove liveFeed state
content = re.sub(r'const \[liveFeed, setLiveFeed\] = useState<LiveInvoice\[\]>\(\[\]\);\n\s*', '', content)

# Remove the fetch endpoint for api/invoices/live-feed
content = re.sub(r'\s*`${API_BASE}/api/invoices/live-feed\?days=7&per_day=20`,', '', content)

# Update index handling
# Now `live-feed` is gone.
# Old indexes:
# 0: dashboard/live
# 1: invoices/live-feed (REMOVED)
# 2: admin/ingestion-status -> now 1
# 3: admin/email-status -> now 2
# 4: admin/sms-status -> now 3
# 5: live-payment-events -> now 4
# 6: version -> now 5
# 7: today-bills -> now 6
# 8: today-payments -> now 7

content = content.replace("responses[2]", "responses[1]")
content = content.replace("responses[3]", "responses[2]")
content = content.replace("responses[4]", "responses[3]")
content = content.replace("responses[5]", "responses[4]")
content = content.replace("responses[6]", "responses[5]")
content = content.replace("responses[7]", "responses[6]")
content = content.replace("responses[8]", "responses[7]")

# Remove the line setting liveFeed
content = re.sub(r'\s*const liveFeed = responses\[\d+\] && responses\[\d+\]\.ok \? await responses\[\d+\]\.json\(\) : null;\n\s*console\.log\("LIVE_FEED_RESPONSE:", liveFeed\);\n\s*if \(liveFeed\) setLiveFeed\(liveFeed\);', '', content)

# There's a check for responses[1].status === 401 which was for live-feed
# Change it to responses[0].status === 401
content = re.sub(r'responses\[1\] && responses\[1\]\.status === 401', 'responses[0] && responses[0].status === 401', content)

# There's a check `(!responses[0] || !responses[0].ok) && (!responses[1] || !responses[1].ok)`
content = re.sub(r'\(\!responses\[1\] \|\| \!responses\[1\]\.ok\) && \!loading', '!loading', content)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("DashboardPage.tsx fetch logic cleaned")
