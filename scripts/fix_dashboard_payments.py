import re

filepath = r"C:\Users\kaila\aradhana-payment-auditor\aradhana-payment-auditor\frontend\src\pages\DashboardPage.tsx"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Replace the endpoints array and fetch assignment
old_endpoints = """      const endpoints = [
        `${API_BASE}/api/dashboard/live`,
        `${API_BASE}/api/admin/ingestion-status`,
        `${API_BASE}/api/admin/email-status`,
        `${API_BASE}/api/admin/sms-status`,
        `${API_BASE}/api/version`
      ];"""

new_endpoints = """      const endpoints = [
        `${API_BASE}/api/dashboard/live`,
        `${API_BASE}/api/admin/ingestion-status`,
        `${API_BASE}/api/admin/email-status`,
        `${API_BASE}/api/admin/sms-status`,
        `${API_BASE}/api/live-payment-events`,
        `${API_BASE}/api/version`
      ];"""

content = content.replace(old_endpoints, new_endpoints)

old_assignments = """      if (responses[4] && responses[4].ok) {
         const vData = await (responses[4] as Response).json();
         setAppVersion(vData.version);
      }"""

new_assignments = """      if (responses[4] && responses[4].ok) setPaymentEvents(await (responses[4] as Response).json());
      if (responses[5] && responses[5].ok) {
         const vData = await (responses[5] as Response).json();
         setAppVersion(vData.version);
      }"""

content = content.replace(old_assignments, new_assignments)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("DashboardPage.tsx successfully fixed")
