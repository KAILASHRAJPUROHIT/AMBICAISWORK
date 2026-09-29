# Private Server2k22 profile store route

Purpose: let the AWS notifier mount only `D:\AradhanaPaymentAuditor` through an encrypted WireGuard tunnel. SMB is never exposed to the public internet.

Topology:

```text
AWS notifier host (10.241.77.1) -- WireGuard UDP/51820 --> Server2k22 (10.241.77.2 / LAN 192.168.0.100)
                                                              |
                                                              +-- D:\AradhanaPaymentAuditor
```

## Security rules

- Create one local Server2k22 account exclusively for this service. Grant it Modify only on `D:\AradhanaPaymentAuditor`, not the entire `D:` drive.
- Permit AWS security-group ingress only for UDP `51820`. Do not add TCP `445` or any SMB port to AWS.
- Permit Server2k22 inbound SMB only from WireGuard IP `10.241.77.1`.
- Keep private keys and SMB credentials outside Git. Scripts create files with restricted permissions.
- The WireGuard tunnel encrypts transport. The mount uses compatible SMB 3.0 over the private tunnel address.

## One-time setup order

1. On AWS run `sudo bash aws-initialize.sh`. It generates the AWS WireGuard private/public key.
2. Associate an Elastic IP with the AWS instance and use that stable IP/DNS as the client endpoint. EC2's automatic public IPv4 can change after a stop/start. This replaces the existing public IPv4 rather than adding a second endpoint.
3. Add an AWS Security Group inbound rule: **Custom UDP / 51820**, source the office public IP CIDR. If the office IP changes dynamically, update this one rule; do not expose SMB.
4. On Server2k22 install WireGuard from the official installer, then run `New-Server2k22RtgsTunnel.ps1` as Administrator with the AWS public key and public endpoint. It writes `server2k22-rtgs.conf` and prints the Server2k22 public key.
5. Back on AWS run `sudo bash aws-add-server2k22-peer.sh <SERVER2K22_PUBLIC_KEY>`. It enables the tunnel and establishes the private route for Server2k22's WireGuard address `10.241.77.2`.
6. Verify from AWS: `nc -zvw 5 10.241.77.2 445`.
7. Create `/etc/samba/credentials/server2k22-rtgs` manually, mode `600`, with the restricted Server2k22 service account. Do not paste its contents into terminal history or Git.
8. On AWS run `sudo bash mount-server2k22-profile-store.sh`, then `sudo bash aws-install-rtgs-profile-store-service.sh` so the mount survives a reboot.
9. In `/opt/aradhana-payment-notifier/deployment/aws/.env`, set `RTGS_PROFILE_STORE_DIR=/mnt/server2k22-d/AradhanaPaymentAuditor`, then redeploy the notifier.

The profile-store backend already persists remitter, B2B, and B2C data. The mount changes its durable location to the Server2k22 folder.
