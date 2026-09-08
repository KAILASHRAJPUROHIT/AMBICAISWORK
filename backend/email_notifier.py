import smtplib
import os
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger("EmailNotifier")

# Feature Flag for Legacy Alerts
LEGACY_ALERT_EMAILS_ENABLED = os.getenv("LEGACY_ALERT_EMAILS_ENABLED", "false").lower() in ('true', '1', 't')
if not LEGACY_ALERT_EMAILS_ENABLED:
    logger.warning("LEGACY_ALERT_EMAILS_ENABLED is false. All security/red alerts will be suppressed.")

# Mandate: Security alerts destination
SECURITY_ALERT_EMAIL = "kuldeeprajpurohit309@gmail.com"

def send_email(to_email: str, subject: str, html_body: str):
    """Base email sender."""
    smtp_server = os.getenv("EMAIL_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("EMAIL_PORT", "587"))
    sender_email = os.getenv("EMAIL_USERNAME")
    sender_password = os.getenv("EMAIL_PASSWORD")

    if not sender_email or not sender_password:
        logger.error("Email credentials not configured in .env")
        return False

    msg = MIMEMultipart()
    msg['From'] = f"Aradhana Auditor <{sender_email}>"
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(html_body, 'html'))

    try:
        logger.info(f"OTP_EMAIL_ATTEMPT to {to_email} via {smtp_server}:{smtp_port}")
        with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
        logger.info(f"OTP_EMAIL_SENT_SUCCESS to {to_email}")
        return True
    except Exception as e:
        logger.error(f"OTP_EMAIL_SEND_FAILED to {to_email}: {str(e)}")
        return False

def send_otp_email(to_email: str, otp_code: str):
    """Sends OTP email for authentication."""
    subject = f"OTP: {otp_code} for Aradhana Payment Auditor"
    body = f"""
    <html>
    <body style="font-family: sans-serif; padding: 20px; color: #333;">
        <h2 style="color: #000;">Authentication Required</h2>
        <p>Your one-time password (OTP) is:</p>
        <div style="background: #f4f4f4; padding: 20px; font-size: 32px; font-weight: bold; text-align: center; border-radius: 10px; margin: 20px 0;">
            {otp_code}
        </div>
        <p>This OTP will expire in 5 minutes.</p>
    </body>
    </html>
    """
    return send_email(to_email, subject, body)

def send_security_alert(event_type: str, details: str):
    """Immediately notifies owner of critical security events."""
    if not LEGACY_ALERT_EMAILS_ENABLED:
        logger.warning(f"Legacy alert email suppressed. Event: {event_type}")
        return True # Return success to prevent crashing the caller

    subject = f"CRITICAL SECURITY ALERT: {event_type}"
    body = f"""
    <html>
    <body style="font-family: sans-serif; padding: 20px; color: #333;">
        <h2 style="color: #d32f2f;">CRITICAL SECURITY ALERT</h2>
        <p>A severe security event has been detected by Aradhana Auditor.</p>
        <div style="background: #fff1f0; border-left: 5px solid #d32f2f; padding: 20px; margin: 20px 0;">
            <strong>Event:</strong> {event_type}<br/>
            <strong>Timestamp:</strong> {logging.Formatter('%(asctime)s').format(logging.LogRecord('',0,'','',0,'','',None))}<br/>
            <strong>Details:</strong> {details}
        </div>
        <p>Please log in to the Master Console immediately to review.</p>
    </body>
    </html>
    """
    # Force delivery to the security alert email
    return send_email(SECURITY_ALERT_EMAIL, subject, body)

def send_financial_alert(event_type: str, invoice_no: str, amount: float):
    """Notifies owner of high-risk financial events."""
    subject = f"FINANCIAL ALERT: {event_type} - {invoice_no}"
    body = f"""
    <html>
    <body style="font-family: sans-serif; padding: 20px; color: #333;">
        <h2 style="color: #ed6c02;">HIGH RISK FINANCIAL EVENT</h2>
        <div style="background: #fff7ed; border-left: 5px solid #ed6c02; padding: 20px; margin: 20px 0;">
            <strong>Event:</strong> {event_type}<br/>
            <strong>Invoice:</strong> {invoice_no}<br/>
            <strong>Amount:</strong> ₹{amount:,.2f}
        </div>
        <p>Verification is required before this transaction can be cleared.</p>
    </body>
    </html>
    """
    return send_email(SECURITY_ALERT_EMAIL, subject, body)

def send_red_alert_email(subject: str, body: str):
    """Backward-compatible wrapper for critical alerts."""
    return send_security_alert(event_type=subject, details=body)
