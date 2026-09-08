# Aradhana Payment Auditor

Financial auditing and reconciliation system for Aradhana.

## Setup
1.  **Environment**: Python 3.11, Node.js.
2.  **Dependencies**: Run `pip install -r requirements.txt` (if available) or install `fastapi uvicorn sqlalchemy pdfplumber watchdog`.
3.  **PC2 Mapping**: Ensure `Z:\Aradhana\InvoicePDFs` is mapped to the laptop.

## SSL / HTTPS
The system supports local HTTPS. To enable it:
1.  Generate self-signed certificates and place them in `certs/cert.pem` and `certs/key.pem`.
2.  The backend will automatically detect these files and start in HTTPS mode.
3.  If missing, the system will fall back to HTTP on port 8000.

## Launch
Run `start_aradhana_auditor.bat` to launch all services.

## Security
- **Employee ID Login**: Required for all users.
- **Email OTP**: Mandatory multi-factor authentication.
- **Session Timeout**: Automatic logout after 3 minutes of inactivity.
- **LAN-Only**: Designed for secure, wired LAN operation.
