import pytest
from unittest.mock import MagicMock, patch
from backend.imap_collector import (
    build_imap_config,
    connect_imap,
    fetch_labeled_emails,
    convert_imap_message_to_raw_email,
    collect_bank_emails
)
from backend.schemas import RawEmail
import os
from datetime import datetime

@patch.dict(os.environ, {"IMAP_HOST": "test.imap.com", "IMAP_USER": "user@test.com", "IMAP_PASSWORD": "password123"})
def test_build_imap_config():
    config = build_imap_config()
    assert config["host"] == "test.imap.com"
    assert config["user"] == "user@test.com"
    assert config["password"] == "password123"

@patch.dict(os.environ, {}, clear=True)
def test_build_imap_config_missing_credentials():
    with pytest.raises(ValueError) as exc_info:
        build_imap_config()
    assert "IMAP credentials" in str(exc_info.value)

@patch("imaplib.IMAP4_SSL")
def test_connect_imap(mock_imap):
    mock_instance = mock_imap.return_value
    config = {"host": "test.imap.com", "user": "user@test.com", "password": "password123"}
    
    conn = connect_imap(config)
    
    mock_imap.assert_called_with("test.imap.com")
    mock_instance.login.assert_called_with("user@test.com", "password123")
    assert conn == mock_instance

@patch("imaplib.IMAP4_SSL")
def test_fetch_labeled_emails_readonly(mock_imap):
    mock_instance = MagicMock()
    mock_instance.select.return_value = ('OK', b'50')
    mock_instance.search.return_value = ('OK', [b'1 2 3'])
    # Mock fetch to return a simple email structure
    mock_instance.fetch.return_value = ('OK', [(b'1 (RFC822 {100}', b'From: test@test.com\r\nSubject: Test\r\nMessage-ID: <123>\r\n\r\nBody')])
    
    raw_emails = fetch_labeled_emails(mock_instance, "BANK_ICICI", limit=50)
    
    # Verify SELECT was called with readonly=True
    mock_instance.select.assert_called_with("BANK_ICICI", readonly=True)
    assert len(raw_emails) == 3
    assert b"From: test@test.com" in raw_emails[0]

def test_convert_imap_message_to_raw_email():
    raw_msg = (
        b"From: sender@bank.com\r\n"
        b"Subject: Bank Alert\r\n"
        b"Message-ID: <msg-789>\r\n"
        b"Date: Mon, 27 Oct 2023 10:00:00 +0530\r\n"
        b"\r\n"
        b"Transaction of 5000.00 confirmed."
    )
    
    raw_email = convert_imap_message_to_raw_email(raw_msg, "BANK_HDFC")
    
    assert isinstance(raw_email, RawEmail)
    assert raw_email.message_id == "<msg-789>"
    assert raw_email.sender == "sender@bank.com"
    assert raw_email.subject == "Bank Alert"
    assert "5000.00" in raw_email.raw_body
    assert raw_email.label == "BANK_HDFC"

def test_convert_imap_message_to_raw_email_with_mime_decoding():
    # RFC 2047 encoded headers
    # Subject: =?utf-8?B?QmFuayBBbGVydDogMTUwMC4wMCDigrk=?= -> Bank Alert: 1500.00 ₹
    # From: =?utf-8?Q?S=C3=A9nder?= <sender@bank.com> -> Sénder <sender@bank.com>
    raw_msg = (
        b"From: =?utf-8?Q?S=C3=A9nder?= <sender@bank.com>\r\n"
        b"Subject: =?utf-8?B?QmFuayBBbGVydDogMTUwMC4wMCDigrk=?=\r\n"
        b"Message-ID: <msg-mime-123>\r\n"
        b"Date: Mon, 27 Oct 2023 10:00:00 +0530\r\n"
        b"\r\n"
        b"Transaction confirmed."
    )
    
    raw_email = convert_imap_message_to_raw_email(raw_msg, "BANK_SBI")
    
    assert raw_email.sender == "Sénder <sender@bank.com>"
    assert raw_email.subject == "Bank Alert: 1500.00 ₹"
    assert raw_email.message_id == "<msg-mime-123>"

@patch("backend.imap_collector.fetch_labeled_emails")
@patch("backend.imap_collector.convert_imap_message_to_raw_email")
def test_collect_bank_emails_skips_duplicates(mock_convert, mock_fetch):
    # Fetch returns 1 message for each label
    mock_fetch.return_value = [b"msg1"]
    
    # Simulate same message across different labels
    # 2 labels -> 2 calls to fetch_labeled_emails -> 2 calls to convert_imap_message_to_raw_email
    mock_convert.side_effect = [
        RawEmail(message_id="id1", sender="s1", subject="sub1", date=datetime.now(), raw_body="b1", label="L1"),
        RawEmail(message_id="id1", sender="s1", subject="sub1", date=datetime.now(), raw_body="b1", label="L2")
    ]
    
    mock_conn = MagicMock()
    collected = collect_bank_emails(mock_conn, ["L1", "L2"])
    
    assert len(collected) == 1
    assert collected[0].message_id == "id1"
    assert mock_convert.call_count == 2

@patch("imaplib.IMAP4_SSL")
def test_verify_no_unsafe_operations(mock_imap):
    mock_instance = MagicMock()
    mock_instance.select.return_value = ('OK', b'50')
    mock_instance.search.return_value = ('OK', [b'1'])
    mock_instance.fetch.return_value = ('OK', [(b'1', b'raw')])
    
    # Run a collection session
    collect_bank_emails(mock_instance, ["BANK_ICICI"])
    
    # Verify no state-modifying commands were called
    assert not mock_instance.store.called
    assert not mock_instance.expunge.called
    assert not mock_instance.copy.called
    assert not mock_instance.move.called
    # Select should only be called with readonly=True
    for call in mock_instance.select.call_args_list:
        assert call.kwargs.get('readonly') is True
