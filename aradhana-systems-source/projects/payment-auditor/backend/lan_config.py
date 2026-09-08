import socket
import logging
import subprocess
import os
from fastapi import Request, HTTPException

logger = logging.getLogger("LAN_Check")

# Approved Subnets for Aradhana LAN
# Production uses 192.168.0.x.  Keep the former private ranges for existing
# installations, otherwise valid shop PCs are falsely logged as unauthorised.
APPROVED_SUBNETS = ["192.168.0.", "192.168.1.", "10.0.0.", "172.16.0."]

def is_physical_lan_connected() -> bool:
    """
    Checks if the system has an active Ethernet (physical) connection.
    On Windows, uses 'netsh interface show interface'.
    """
    if os.name != 'nt':
        # Fallback for non-windows (though production is win32)
        return True 
        
    try:
        # Check for interfaces that are 'Ethernet' and 'Connected'
        output = subprocess.check_output("netsh interface show interface", shell=True).decode()
        lines = output.splitlines()
        
        has_ethernet = False
        wifi_connected = False
        
        for line in lines:
            if "Ethernet" in line and "Connected" in line:
                has_ethernet = True
            if "Wi-Fi" in line and "Connected" in line:
                wifi_connected = True
                
        # Mandate: Physical LAN REQUIRED, WiFi NOT ALLOWED
        if wifi_connected and not has_ethernet:
             logger.warning("WiFi detected without Ethernet. Production Actions Blocked.")
             return False
             
        return has_ethernet
    except Exception as e:
        logger.error(f"Error checking LAN status: {e}")
        return True # Default to allow if check fails to avoid total lockout

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
        return False
        
    # Check physical connection for mutation requests
    if request.method in ["POST", "PUT", "DELETE"]:
        if not is_physical_lan_connected():
            logger.critical("MUTATION BLOCKED: Physical LAN connection required.")
            return False
            
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
