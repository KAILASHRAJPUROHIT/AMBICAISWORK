# AWS staging deployment: QR Print Server

This runs only the cloud API and queue. PC2 and Dell remain local gateway machines because AWS cannot directly operate their Windows printer drivers or Ornate windows.

## Before first deployment

1. Create and mount the persistent EBS volume at `/srv/aradhana-print`.
2. Install Docker Engine and Docker Compose plugin on the VM.
3. Copy this repository to the VM. Do not copy local `uploads`, `jobs.db`, `.env`, logs, or a local agent workspace.
4. Copy `.env.example` to `.env`, then populate the existing bridge token and a fresh, separate `AGENT_TOKEN`.
5. Restrict the VM security group: SSH only from the office admin IP; do not expose port 8000 publicly. TLS reverse proxy is added only after staging health and PC gateways pass.

`deploy-aws.sh` creates the mounted data directory as the unprivileged container account (`uid/gid 10001`). Do not change it to world-writable permissions.

## Start and verify

```bash
cd deployment/aws
chmod 700 deploy-aws.sh
./deploy-aws.sh
docker compose logs --tail=100 qr-print-server
```

Expected health response: JSON with `status` healthy/ok. This is staging only until one managed PC2 gateway completes a real direct-to-P355 job and one send-to-biller document claim.

## Rollback

Keep the previous image tag and deployment checkout. To return to Render, leave PC2/Dell `CLOUD_SERVER_URL` unchanged. To revert an AWS code deployment, check out the previous verified commit and run `./deploy-aws.sh`; data stays on the EBS volume.

Never delete `/srv/aradhana-print/data` during a rollback. It contains queued documents and the database.
