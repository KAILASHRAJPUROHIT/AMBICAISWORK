# Physical Firewall & Deployment Recommendations

To ensure maximum financial integrity and security for the Aradhana Auditor, the following deployment strategy is recommended:

## 1. Network Segmentation (LAN-Only)
*   **Wired LAN Only**: All core components (Auditor Laptop, PC2 Billing Machine, App Server) MUST be connected via wired Ethernet. Disable Wi-Fi on these machines to prevent wireless intercept or unauthorized access.
*   **Approved Subnet**: The auditor is configured to only accept requests from the approved local subnet (e.g., `192.168.1.0/24`).

## 2. Hardware Firewall
*   **Dedicated Router/Firewall**: Deploy a dedicated hardware firewall (e.g., pfSense, OPNsense, or a managed Ubiquiti/Cisco router) between the Auditor LAN and the rest of the building/internet.
*   **Block Inbound Access**: Configure the firewall to block ALL inbound traffic from the internet. Port forwarding is STRICTLY PROHIBITED.
*   **Walled Garden**: Allow only required LAN ports for the Auditor:
    *   `8000` (HTTPS Backend)
    *   `5173` (Frontend)
    *   `445` (SMB for Z: drive share)

## 3. Android SMS Collector
*   **Local Route Only**: The Android phone acting as the SMS collector should be connected to the approved LAN via a secure local route (e.g., a dedicated local Wi-Fi AP bridged to the wired LAN with strict MAC filtering).
*   **No Cloud Sync**: SMS data should be polled directly from the phone via a local API; do not use cloud-based SMS sync services.

## 4. HTTPS & Local SSL
*   **Self-Signed Certs**: The system uses local self-signed certificates for HTTPS.
*   **Installation**: To avoid browser warnings on the LAN, manually install the `certs/cert.pem` as a "Trusted Root Certification Authority" on the auditor laptop and any other authorized viewing machines.

## 5. Remote Access (Optional)
*   **Zero Trust**: If the owner requires remote access, DO NOT open ports. Instead, use **Cloudflare Zero Trust** or a **Tailscale/Wireguard VPN** with Employee ID + OTP enforced at the tunnel level.
