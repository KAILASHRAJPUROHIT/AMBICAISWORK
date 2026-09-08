import imaplib
import os
import json
from dotenv import load_dotenv

load_dotenv()

def check_labels():
    user = os.getenv("IMAP_USER")
    password = os.getenv("IMAP_PASSWORD")
    host = os.getenv("IMAP_HOST", "imap.gmail.com")
    
    print(f"Connecting to {host} as {user}...")
    try:
        mail = imaplib.IMAP4_SSL(host)
        mail.login(user, password)
        status, folders = mail.list()
        if status == 'OK':
            print("Labels found:")
            for f in folders:
                print(f.decode())
        mail.logout()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_labels()
