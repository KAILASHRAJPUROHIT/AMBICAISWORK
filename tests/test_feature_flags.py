import os
import importlib
from unittest.mock import patch, MagicMock

# We need to import the module under test
from backend import email_notifier

def test_otp_email_unaffected_by_flag_disabled_by_default():
    """
    Ensures that OTP emails are ALWAYS sent, regardless of the legacy alert flag.
    By default, LEGACY_ALERT_EMAILS_ENABLED is False.
    """
    with patch('backend.email_notifier.send_email') as mock_send_email:
        mock_send_email.return_value = True
        
        # Call the OTP email function
        result = email_notifier.send_otp_email("test@example.com", "123456")
        
        # Assert that the base sender was called and the function returned True
        mock_send_email.assert_called_once()
        assert result is True

@patch.dict(os.environ, {"LEGACY_ALERT_EMAILS_ENABLED": "false"})
def test_security_alert_suppressed_when_flag_is_false():
    """
    Verifies that security alerts are suppressed when the feature flag is 'false'.
    """
    # Reload the module to ensure it picks up the patched environment variable
    importlib.reload(email_notifier)
    
    with patch('backend.email_notifier.send_email') as mock_send_email:
        # Call the security alert function
        result = email_notifier.send_security_alert("TEST_EVENT", "Some details")
        
        # Assert that the base sender was NOT called
        mock_send_email.assert_not_called()
        # Assert that the function returns True to not break workflows
        assert result is True

@patch.dict(os.environ, {"LEGACY_ALERT_EMAILS_ENABLED": "true"})
def test_security_alert_sent_when_flag_is_true():
    """
    Verifies that security alerts are sent when the feature flag is 'true'.
    """
    # Reload the module to ensure it picks up the patched environment variable
    importlib.reload(email_notifier)
    
    with patch('backend.email_notifier.send_email') as mock_send_email:
        mock_send_email.return_value = True
        
        # Call the security alert function
        result = email_notifier.send_security_alert("TEST_EVENT", "Some details")
        
        # Assert that the base sender WAS called
        mock_send_email.assert_called_once()
        assert result is True

def test_red_alert_wrapper_is_suppressed():
    """
    Verifies that the red alert wrapper is also suppressed by the flag.
    """
    # Ensure flag is default (off)
    os.environ["LEGACY_ALERT_EMAILS_ENABLED"] = "false"
    importlib.reload(email_notifier)

    with patch('backend.email_notifier.send_email') as mock_send_email:
        # Call the red alert wrapper function
        result = email_notifier.send_red_alert_email("RED_ALERT_SUBJECT", "Some body")

        # Assert that the base sender was NOT called
        mock_send_email.assert_not_called()
        assert result is True
