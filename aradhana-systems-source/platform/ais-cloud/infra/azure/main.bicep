targetScope = 'resourceGroup'

@description('Azure region selected for the AIS production environment.')
param location string = resourceGroup().location

@description('Globally unique lowercase prefix, 3-12 characters. Example: aradhanaais.')
@minLength(3)
@maxLength(12)
param namePrefix string

@description('Immutable container image reference in Azure Container Registry.')
param gatewayImage string

@secure()
@description('PostgreSQL connection URL. Provision the database in the private-network phase, then redeploy this secret.')
param databaseUrl string

@secure()
param agentToken string

@secure()
param ownerToken string

@secure()
param adminCredentialHash string

@secure()
param sessionSecret string

var suffix = toLower(uniqueString(subscription().id, resourceGroup().id, namePrefix))
var keyVaultName = '${namePrefix}kv${take(suffix, 8)}'
var storageName = '${namePrefix}st${take(suffix, 10)}'
var registryName = '${namePrefix}acr${take(suffix, 8)}'
var environmentName = '${namePrefix}-aca'
var identityName = '${namePrefix}-gateway-id'
var gatewayName = '${namePrefix}-gateway'

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${namePrefix}-logs'
  location: location
  properties: {
    retentionInDays: 30
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
      disableLocalAuth: false
    }
  }
  sku: {
    name: 'PerGB2018'
  }
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  properties: {
    enableRbacAuthorization: true
    enablePurgeProtection: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    accessPolicies: []
    publicNetworkAccess: 'Enabled'
  }
}

resource agentTokenSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'ais-agent-token'
  properties: { value: agentToken }
}

resource ownerTokenSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'ais-owner-token'
  properties: { value: ownerToken }
}

resource adminCredentialHashSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'ais-admin-credential-hash'
  properties: { value: adminCredentialHash }
}

resource sessionSecretSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'ais-session-secret'
  properties: { value: sessionSecret }
}

resource databaseUrlSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'ais-database-url'
  properties: { value: databaseUrl }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    publicNetworkAccess: 'Enabled'
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource protectedDocuments 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'ais-private'
  properties: { publicAccess: 'None' }
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: registryName
  location: location
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

resource managedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: identityName
  location: location
}

resource keyVaultSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, managedIdentity.properties.principalId, 'Key Vault Secrets User')
  scope: keyVault
  properties: {
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
  }
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, managedIdentity.properties.principalId, 'AcrPull')
  scope: registry
  properties: {
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  }
}

resource managedEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: environmentName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

resource gateway 'Microsoft.App/containerApps@2024-03-01' = {
  name: gatewayName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: managedEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      registries: [{
        server: registry.properties.loginServer
        identity: managedIdentity.id
      }]
      ingress: {
        external: true
        allowInsecure: false
        targetPort: 8080
        transport: 'auto'
      }
      secrets: [
        { name: 'database-url', keyVaultUrl: '${keyVault.properties.vaultUri}secrets/ais-database-url', identity: managedIdentity.id }
        { name: 'agent-token', keyVaultUrl: '${keyVault.properties.vaultUri}secrets/ais-agent-token', identity: managedIdentity.id }
        { name: 'owner-token', keyVaultUrl: '${keyVault.properties.vaultUri}secrets/ais-owner-token', identity: managedIdentity.id }
        { name: 'admin-credential-hash', keyVaultUrl: '${keyVault.properties.vaultUri}secrets/ais-admin-credential-hash', identity: managedIdentity.id }
        { name: 'session-secret', keyVaultUrl: '${keyVault.properties.vaultUri}secrets/ais-session-secret', identity: managedIdentity.id }
      ]
    }
    template: {
      containers: [{
        name: 'ais-gateway'
        image: gatewayImage
        env: [
          { name: 'AIS_ENVIRONMENT', value: 'production' }
          { name: 'AIS_DATABASE_URL', secretRef: 'database-url' }
          { name: 'AIS_AGENT_TOKEN', secretRef: 'agent-token' }
          { name: 'AIS_OWNER_TOKEN', secretRef: 'owner-token' }
          { name: 'AIS_ADMIN_CREDENTIAL_HASH', secretRef: 'admin-credential-hash' }
          { name: 'AIS_SESSION_SECRET', secretRef: 'session-secret' }
          { name: 'AIS_ALLOWED_ORIGINS', value: 'https://ais.aradhanajewellers.com' }
        ]
        resources: {
          cpu: json('0.5')
          memory: '1Gi'
        }
        probes: [{
          type: 'Liveness'
          httpGet: { path: '/health', port: 8080 }
          initialDelaySeconds: 10
          periodSeconds: 15
        }, {
          type: 'Readiness'
          httpGet: { path: '/health', port: 8080 }
          initialDelaySeconds: 5
          periodSeconds: 10
        }]
      }]
      scale: {
        minReplicas: 1
        maxReplicas: 3
      }
    }
  }
  dependsOn: [
    keyVaultSecretsUser
    acrPull
    agentTokenSecret
    ownerTokenSecret
    adminCredentialHashSecret
    sessionSecretSecret
    databaseUrlSecret
  ]
}

output gatewayFqdn string = gateway.properties.configuration.ingress.fqdn
output keyVaultUri string = keyVault.properties.vaultUri
output registryLoginServer string = registry.properties.loginServer
output privateBlobContainer string = protectedDocuments.name
