import urllib.request
import json

def call(url):
    print(f"Calling: {url}")
    req = urllib.request.Request(url, headers={'X-Session-Token': 'DIAG_TOKEN_123'})
    try:
        with urllib.request.urlopen(req) as res:
            body = res.read().decode()
            print(f"  Result: {res.getcode()}")
            print(f"  Body: {body[:200]}")
    except urllib.error.HTTPError as e:
        print(f"  Error {e.code}: {e.read().decode()}")
    except Exception as e:
        print(f"  Error: {e}")

if __name__ == "__main__":
    call('http://127.0.0.1:8000/api/dashboard/live')
    call('http://127.0.0.1:8000/api/invoices/live-feed')
    call('http://127.0.0.1:8000/api/auth/me')
