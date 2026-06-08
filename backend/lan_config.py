import socket
import logging
import subprocess
import os
from fastapi import Request, HTTPException

logger = logging.getLogger("LAN_Check")

import ipaddress

def is_physical_lan_connected() -> bool:
    if os.name != 'nt':
        return True 
        
    try:
        output = subprocess.check_output("netsh interface show interface", shell=True).decode()
        lines = output.splitlines()
        
        has_ethernet = False
        wifi_connected = False
        
        for line in lines:
            if "Ethernet" in line and "Connected" in line:
                has_ethernet = True
            if "Wi-Fi" in line and "Connected" in line:
                wifi_connected = True
                
        if wifi_connected and not has_ethernet:
             logger.warning("WiFi detected without Ethernet. Production Actions Blocked.")
             return False
             
        return has_ethernet
    except Exception as e:
        logger.error(f"Error checking LAN status: {e}")
        return True

def is_on_approved_lan(ip_address: str) -> bool:
    if ip_address == "127.0.0.1" or ip_address == "::1":
        return True
        
    shop_cidr = os.getenv("SHOP_LAN_ALLOWED_CIDRS")
    if not shop_cidr:
        return False
        
    try:
        client_ip_obj = ipaddress.ip_address(ip_address)
        cidrs = [c.strip() for c in shop_cidr.split(',')]
        for c in cidrs:
            network_obj = ipaddress.ip_network(c, strict=False)
            if client_ip_obj in network_obj:
                return True
        return False
    except ValueError:
        return False

def check_owner_wifi_access(request: Request, db, token: str):
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
        
    client_ip = request.client.host
    if not is_on_approved_lan(client_ip):
        raise HTTPException(status_code=403, detail="Network access denied. Must be on Shop LAN.")
        
    from backend.auth_service import validate_session
    from backend.models import User
    try:
        employee_id = validate_session(db, token)
        if not employee_id:
            raise Exception("Invalid session")
        user = db.query(User).filter(User.employee_id == employee_id).first()
        if not user or user.role.upper() != "OWNER":
            raise HTTPException(status_code=403, detail="Owner privileges required")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid session")
    return True

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
