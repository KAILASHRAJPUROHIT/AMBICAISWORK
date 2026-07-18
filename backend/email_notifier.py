import smtplib
import os
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger("EmailNotifier")

def send_email(to_email: str, subject: str, html_body: str, from_name: str = "Payment Auditor"):
    """Base email sender."""
    smtp_server = os.getenv("EMAIL_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("EMAIL_PORT", "587"))
    sender_email = os.getenv("EMAIL_USERNAME")
    sender_password = os.getenv("EMAIL_PASSWORD")

    if not sender_email or not sender_password:
        logger.error("Email credentials not configured in .env")
        return False

    msg = MIMEMultipart()
    msg['From'] = f"{from_name} <{sender_email}>"
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

def send_otp_email(to_email: str, otp_code: str, business_name: str = "Payment Auditor"):
    """Sends OTP email for authentication.
    business_name: the tenant's own name, resolved by the caller from its
    business profile (see review_api.py's login/verify/resend-otp handlers)
    — this used to be a hardcoded "Aradhana Payment Auditor" regardless of
    which business the OTP was actually for."""
    subject = f"OTP: {otp_code} for {business_name}"
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
    return send_email(to_email, subject, body, from_name=business_name)

def send_security_alert(event_type: str, details: str, alert_emails: list[str], business_name: str = "Payment Auditor"):
    """Immediately notifies a tenant's configured recipients of critical
    security events. alert_emails comes from that tenant's own business
    profile (business_registry.py's alert_emails field) — this used to be
    a single hardcoded personal Gmail address, force-used for every tenant
    regardless of who the alert was actually about. Currently unused
    (no caller wires this up yet), but fixed here so it can't be
    reactivated with the old hardcoded-recipient bug."""
    if not alert_emails:
        logger.warning(f"send_security_alert: no alert_emails configured, dropping alert: {event_type}")
        return False
    subject = f"CRITICAL SECURITY ALERT: {event_type}"
    body = f"""
    <html>
    <body style="font-family: sans-serif; padding: 20px; color: #333;">
        <h2 style="color: #d32f2f;">CRITICAL SECURITY ALERT</h2>
        <p>A severe security event has been detected by {business_name}.</p>
        <div style="background: #fff1f0; border-left: 5px solid #d32f2f; padding: 20px; margin: 20px 0;">
            <strong>Event:</strong> {event_type}<br/>
            <strong>Timestamp:</strong> {logging.Formatter('%(asctime)s').format(logging.LogRecord('',0,'','',0,'','',None))}<br/>
            <strong>Details:</strong> {details}
        </div>
        <p>Please log in to the Master Console immediately to review.</p>
    </body>
    </html>
    """
    return all(send_email(addr, subject, body, from_name=business_name) for addr in alert_emails)

def send_red_alert_email(subject: str, body: str, alert_emails: list[str], business_name: str = "Payment Auditor"):
    """Ingestion-pipeline red alerts (PDF parse failure, payment-total
    mismatch) — see pdf_ingestion.py's process_invoice. This function was
    called from two places there but never actually existed anywhere in
    the codebase; every real call to either would have raised ImportError
    at the exact moment something needed a human's attention (a parse
    failure or a payment mismatch on a real invoice)."""
    if not alert_emails:
        logger.warning(f"send_red_alert_email: no alert_emails configured, dropping alert: {subject}")
        return False
    html_body = f"""
    <html>
    <body style="font-family: sans-serif; padding: 20px; color: #333;">
        <h2 style="color: #d32f2f;">RED ALERT — {business_name}</h2>
        <div style="background: #fff1f0; border-left: 5px solid #d32f2f; padding: 20px; margin: 20px 0; white-space: pre-wrap;">{body}</div>
    </body>
    </html>
    """
    return all(send_email(addr, subject, html_body, from_name=business_name) for addr in alert_emails)

def send_financial_alert(event_type: str, invoice_no: str, amount: float, alert_emails: list[str], business_name: str = "Payment Auditor"):
    """Notifies a tenant's configured recipients of high-risk financial
    events. See send_security_alert's docstring — same fix, same reason."""
    if not alert_emails:
        logger.warning(f"send_financial_alert: no alert_emails configured, dropping alert: {event_type} {invoice_no}")
        return False
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
    return all(send_email(addr, subject, body, from_name=business_name) for addr in alert_emails)
