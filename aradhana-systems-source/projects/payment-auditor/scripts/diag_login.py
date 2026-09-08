import urllib.request
import json

def test_login(id, pw):
    url = 'http://127.0.0.1:8000/api/auth/login'
    data = json.dumps({'employee_id': id, 'password': pw}).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req) as res:
            print(f"PASS {id}:{pw} -> {res.getcode()} {res.read().decode()}")
    except urllib.error.HTTPError as e:
        print(f"FAIL {id}:{pw} -> {e.code} {e.read().decode()}")
    except Exception as e:
        print(f"ERR  {id}:{pw} -> {e}")

if __name__ == "__main__":
    test_login('OWNER-01', 'Owner@123')
    test_login('OWNER-01', 'wrong_pass')
    test_login('BAD_USER', 'some_pass')
    test_login('', '')
