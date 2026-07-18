"""
lan_config.py — was a physical-LAN-only access gate for the single-business
desktop deployment (Windows Ethernet-vs-WiFi detection, a hardcoded
APPROVED_SUBNETS allowlist). None of that means anything on a hosted SaaS
deployment: there is no "the office LAN" to be on, "unauthorized IP"
warnings would fire for every legitimate cloud request, and the physical-
Ethernet check shells out to a Windows-only `netsh` command that wouldn't
even run on a typical Linux host.

Kept as a thin compatibility module (same function names/signatures) rather
than deleted outright, since a few endpoints still import from it — every
function here is now a permissive no-op. If a specific tenant genuinely
wants to self-host on their own LAN with this restriction re-enabled later,
that's a per-tenant opt-in setting to build, not the platform default.
"""
import socket


def is_physical_lan_connected() -> bool:
    return True


def is_on_approved_lan(ip_address: str) -> bool:
    return True


async def lan_health_check(request) -> bool:
    return True


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP
