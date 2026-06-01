import logging

logger = logging.getLogger("EmailNotifier")

def send_red_alert_email(subject, body, recipients=None):
    if recipients is None:
        recipients = ["admin@aradhana.local"]
    
    # Mock sending email logic
    logger.error("=" * 60)
    logger.error(f"URGENT RED ALERT NOTIFICATION SENT TO {recipients}")
    logger.error(f"Subject: {subject}")
    logger.error(f"Body:\n{body}")
    logger.error("=" * 60)
