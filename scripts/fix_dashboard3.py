import re

filepath = r"C:\Users\kaila\aradhana-payment-auditor\aradhana-payment-auditor\frontend\src\pages\DashboardPage.tsx"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Replace fetchData block completely
new_fetch_data = """  const fetchData = async () => {
    const token = getSessionToken();
    const headers = {
      'X-Session-Token': token || ''
    };

    try {
      const endpoints = [
        `${API_BASE}/api/dashboard/live`,
        `${API_BASE}/api/admin/ingestion-status`,
        `${API_BASE}/api/admin/email-status`,
        `${API_BASE}/api/admin/sms-status`,
        `${API_BASE}/api/version`
      ];

      const responses = await Promise.all(endpoints.map(url => 
        fetch(url, { headers }).catch(() => null)
      ));

      const dashboardLive = responses[0] && responses[0].ok ? await responses[0].json() : null;
      console.log("DASHBOARD_LIVE_RESPONSE:", dashboardLive);
      setDashboardApiAvailable(!!dashboardLive);
      if (dashboardLive) setStats(dashboardLive);

      const ingestionStatus = responses[1] && responses[1].ok ? await responses[1].json() : null;
      console.log("INGESTION_STATUS_RESPONSE:", ingestionStatus);
      if (ingestionStatus) setIngestionStatus(ingestionStatus);

      if (responses[2] && responses[2].ok) setEmailStatus(await (responses[2] as Response).json());
      if (responses[3] && responses[3].ok) setSMSStatus(await (responses[3] as Response).json());
      if (responses[4] && responses[4].ok) {
         const vData = await (responses[4] as Response).json();
         setAppVersion(vData.version);
      }

      // Fetch new dashboard split feeds independently
      const [billsRes, paymentsRes] = await Promise.all([
        fetch(`${API_BASE}/api/dashboard/today-bills`, { headers }).catch(() => null),
        fetch(`${API_BASE}/api/dashboard/today-payments`, { headers }).catch(() => null)
      ]);
      
      if (billsRes && billsRes.ok) {
        const billsData = await billsRes.json();
        setTodayBills(Array.isArray(billsData) ? billsData : []);
      } else {
        setTodayBills([]);
      }

      if (paymentsRes && paymentsRes.ok) {
        const paymentsData = await paymentsRes.json();
        setTodayPayments(Array.isArray(paymentsData) ? paymentsData : []);
      } else {
        setTodayPayments([]);
      }

      // Check for auth failure
      if (responses[0] && responses[0].status === 401) {
          setError('Session Expired. Please Login.');
          return;
      }

      // Only show error if core stats or feed fail when NOT loading
      if ((!responses[0] || !responses[0].ok) && !loading) {
          setError('API Connection Lost');
          AlertSoundSystem.playCritical();
      } else {
          setError(null);
      }
      
    } catch (err: any) {
      console.error("Fetch error:", err);
      if (!loading) {
          setError('Backend Unreachable');
          AlertSoundSystem.playCritical();
      }
    } finally {
      setLoading(false);
    }
  };"""

# Replace the old `const fetchData = async () => { ... }` up to the end of `};` right before `useEffect(() => {`
content = re.sub(
    r'const fetchData = async \(\) => \{.*?\}\s*};\n\s*useEffect\(\(\) => \{',
    new_fetch_data + '\n\n  useEffect(() => {',
    content,
    flags=re.DOTALL
)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("DashboardPage.tsx successfully fixed")
