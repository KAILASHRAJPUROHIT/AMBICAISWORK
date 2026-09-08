# AIS Control Center

Local, read-only operational console for the development/control-plane laptop.

* URL after installation: `http://127.0.0.1:8120`
* Binding: loopback only. It deliberately rejects LAN/WAN requests.
* Inputs: `platform\core\ais.registry.json` and `ais.devices.json`.
* Output: declared project inventory and owner-local service health.
* It has no credentials, remote-shell action, print action, update action, or database write endpoint.

## Runtime

`install_ais_control_center.ps1` installs a SYSTEM startup task only because
this component is an HTTP API/UI host. It does not display a biller-facing
window. Interactive AIS agents must instead run in the relevant signed-in user
session.

## Release discipline

Do not ship this source folder directly. Assemble an allow-listed release ZIP
with `..\ota-control\New-AISReleaseBundle.ps1`, sign it with
`publish_release.py`, stage it through beta, then promote only after health
and acceptance evidence are recorded.
