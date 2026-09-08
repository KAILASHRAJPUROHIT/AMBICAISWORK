import urllib.request
import json
token = 'ibpoIPfrhd7okFyRoQvph9eo5qx02NRT'

try:
    req = urllib.request.Request('http://localhost:8010/api/dashboard/today-bills', headers={'X-Session-Token': token})
    with urllib.request.urlopen(req) as response:
        print('TODAY BILLS JSON:', response.read().decode())
except Exception as e:
    print('BILLS ERROR:', e)
    
try:
    req2 = urllib.request.Request('http://localhost:8010/api/dashboard/today-payments', headers={'X-Session-Token': token})
    with urllib.request.urlopen(req2) as response:
        print('TODAY PAYMENTS JSON:', response.read().decode())
except Exception as e:
    print('PAYMENTS ERROR:', e)
