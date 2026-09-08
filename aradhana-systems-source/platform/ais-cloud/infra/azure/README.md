# Azure production deployment

`main.bicep` deploys the AIS gateway baseline: Container Apps Environment, Log Analytics, Key Vault with RBAC, user-assigned identity, private Blob container, Azure Container Registry and one TLS-only Container App with a minimum of one replica.

It deliberately does **not** deploy PostgreSQL yet. A secure PostgreSQL setup needs a VNet/subnet decision and private DNS zone. Do not add a public database firewall exception as a shortcut.

## First deployment

1. Install Azure CLI and sign in to the intended subscription.
2. Create a private parameter file from `main.parameters.example.json` outside `C:\AradhanaSystems` source control.
3. Build/push a tagged gateway image to the newly created Azure Container Registry. The first Bicep run can use a controlled bootstrap image only after review.
4. Run `Deploy-AISAzure.ps1` without `-Apply`. It only performs Azure `what-if`.
5. Review the resource changes. Run again with `-Apply` only after approval.
6. Map `ais.aradhanajewellers.com` at GoDaddy/Cloudflare after the Container App FQDN is returned.

Container Apps can reference Key Vault secrets through a managed identity. The template assigns Key Vault Secrets User to the gateway identity; no production secret is committed. [Microsoft guidance](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets)

Keep `print.aradhanajewellers.com` online. Redirect it only after `/print` passes beta acceptance.
