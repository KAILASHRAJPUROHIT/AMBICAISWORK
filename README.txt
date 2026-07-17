AMBIC SMARTQR - QUICKSTART

1. Install packages:
   pip install -r cloud-server/requirements.txt

2. Run the cloud server:
   cd cloud-server
   python app.py

3. Onboard your business:
   http://YOUR-PC-IP:5000/setup
   Fill in business name, branding, and (optionally) logo, voice clip,
   Instagram/Facebook/Google review/WhatsApp/phone links. Save gives you an
   Agent API Key and Admin Secret - keep both.

4. Open the customer landing page on phone:
   http://YOUR-PC-IP:5000/

5. Set up the local print agent (on the PC with the printer attached):
   cd local-print-agent
   copy .env.example .env
   -- fill in CLOUD_SERVER_URL, PRINTER_NAME, SUMATRA_PATH, TENANT_SLUG,
      AGENT_API_KEY (from step 3) --
   python agent.py
   (see local-print-agent/README.md for running it as a Windows service)

6. Admin queue view:
   http://YOUR-PC-IP:5000/admin?tenant=your-business-slug

Print rules:
- JPG/JPEG/PNG/PDF supported
- Maximum 12 files per upload
- 1 file = 1 PAN-card-size slot
- 6 files = 1 A4 page
- 7-12 files = 2 A4 pages
