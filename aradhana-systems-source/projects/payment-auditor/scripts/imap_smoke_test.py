import os
import sys
from datetime import datetime

# Add the project root to sys.path to allow importing from backend
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("Warning: python-dotenv not installed. Relying on existing environment variables.")

from backend.imap_collector import (
    build_imap_config,
    connect_imap,
    fetch_labeled_emails,
    convert_imap_message_to_raw_email
)

def run_smoke_test():
    """
    Controlled smoke test to verify IMAP connectivity and metadata fetching.
    """
    print(f"[{datetime.now()}] Starting IMAP Smoke Test...")
    
    try:
        # 1. Build Config
        config = build_imap_config()
        print(f"Config built for user: {config['user']}")
        
        # 2. Connect
        print("Connecting to IMAP server...")
        mail = connect_imap(config)
        
        # 3. Fetch (Target label from sys.argv, Limit: 5)
        label = sys.argv[1] if len(sys.argv) > 1 else "BANK_SBI"
        print(f"Fetching latest 5 emails from label: {label} (Read-Only)...")
        raw_msgs = fetch_labeled_emails(mail, label, limit=5)
        
        print(f"Found {len(raw_msgs)} emails.")
        
        # 4. Print Metadata only
        for i, raw_msg in enumerate(raw_msgs, 1):
            raw_email = convert_imap_message_to_raw_email(raw_msg, label)
            if raw_email:
                print(f"\n--- Email {i} ---")
                print(f"ID:     {raw_email.message_id}")
                print(f"From:   {raw_email.sender}")
                print(f"Subj:   {raw_email.subject}")
                print(f"Date:   {raw_email.date}")
            else:
                print(f"\n--- Email {i}: Failed to parse metadata ---")
        
        # 5. Cleanup
        mail.logout()
        print(f"\n[{datetime.now()}] Smoke test completed successfully.")
        
    except Exception as e:
        print(f"\nERROR: Smoke test failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    run_smoke_test()
