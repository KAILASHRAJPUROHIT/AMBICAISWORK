import socket
import logging
from fastapi import Request, HTTPException

logger = logging.getLogger("LAN_Check")

# Approved Subnets for Aradhana LAN
APPROVED_SUBNETS = ["192.168.1.", "10.0.0.", "172.16.0."] 

def is_on_approved_lan(ip_address: str) -> bool:
    if ip_address == "127.0.0.1" or ip_address == "::1":
        return True # Allow localhost for dev
        
    for subnet in APPROVED_SUBNETS:
        if ip_address.startswith(subnet):
            return True
    return False

async def lan_health_check(request: Request):
    client_ip = request.client.host
    if not is_on_approved_lan(client_ip):
        logger.warning(f"Security Alert: Request from unauthorized IP {client_ip}")
        # In strict mode, we might raise an exception
        # For now, we'll just log and return status
        return False
    return True

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP
