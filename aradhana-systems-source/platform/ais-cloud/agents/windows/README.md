# AIS Windows health agent

The agent does one thing: probes services declared for its own device in `platform\core\ais.registry.json`, then sends an outbound HTTPS heartbeat to AIS.

It cannot receive commands, access printers, read customer documents, run shell commands, or open a LAN port.

Production installation will use a protected machine credential and a SYSTEM scheduled task after Azure Key Vault/identity is configured. Do not put a production token in a `.ps1`, `.bat`, registry Run entry or command line.

Development proof:

```powershell
$env:AIS_GATEWAY_URL = 'http://127.0.0.1:8180'
$env:AIS_AGENT_TOKEN = '<development token>'
& 'C:\Users\kaila\AppData\Local\Programs\Python\Python311\python.exe' 'C:\AradhanaSystems\platform\ais-cloud\agents\windows\ais_health_agent.py'
```
