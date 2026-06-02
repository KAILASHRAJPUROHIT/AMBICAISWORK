import smtplib
import os
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger("EmailNotifier")

def send_otp_email(to_email: str, otp_code: str):
    """Sends OTP email to user for authentication."""
    smtp_server = os.getenv("EMAIL_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("EMAIL_PORT", "587"))
    sender_email = os.getenv("EMAIL_USERNAME")
    sender_password = os.getenv("EMAIL_PASSWORD")

    if not sender_email or not sender_password:
        logger.error("Email credentials not configured. Cannot send OTP.")
        return False

    msg = MIMEMultipart()
    msg['From'] = f"Aradhana Auditor <{sender_email}>"
    msg['To'] = to_email
    msg['Subject'] = f"OTP: {otp_code} for Aradhana Payment Auditor"

    body = f"""
    <html>
    <body style="font-family: sans-serif; padding: 20px; color: #333;">
        <h2 style="color: #000;">Authentication Required</h2>
        <p>Your one-time password (OTP) for Aradhana Payment Auditor is:</p>
        <div style="background: #f4f4f4; padding: 20px; font-size: 32px; font-weight: bold; text-align: center; border-radius: 10px; margin: 20px 0;">
            {otp_code}
        </div>
        <p>This OTP will expire in 3 minutes.</p>
        <p style="font-size: 12px; color: #888;">If you did not request this, please ignore this email.</p>
    </body>
    </html>
    """
    msg.attach(MIMEText(body, 'html'))

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
        logger.info(f"OTP email sent to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send OTP email: {e}")
        return False
