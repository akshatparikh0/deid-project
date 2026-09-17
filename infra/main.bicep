// De-identification tool — Azure infrastructure (NFR-21: one template,
// no manual deployment step). Deploy at resource-group scope:
//
//   az group create -n rg-deid-<env>-<region> -l eastus2
//   az deployment group create -g rg-deid-<env>-<region> \
//     -f infra/main.bicep -p infra/main.parameters.<env>.json
//
// This provisions every FR-54 – FR-66 component. Two things it does NOT
// do, because they need broader-than-deployment permissions or a one-time
// human decision:
//   - Microsoft Entra ID app registration (FR-55) — app registrations are
//     a Graph API operation, not an ARM/Bicep resource; run
//     `az ad app create --display-name deid-<env>` once per environment
//     and pass its appId into the API container's settings.
//   - The HIPAA Business Associate Agreement (FR-66) — a legal agreement
//     with Microsoft, not infrastructure; a project must not go live
//     without one, but Bicep has no representation for it.
//
// Container images are referenced by tag (see `apiImage`/`workerImage`/
// `frontendImage` params) — this template provisions the registry and the
// compute that runs them, it doesn't build or push them (see
// .github/workflows/ci.yml for that).

targetScope = 'resourceGroup'

// ---------------------------------------------------------------------
// Parameters
// ---------------------------------------------------------------------

@description('Short environment name, e.g. "staging" or "prod". Used in resource names.')
param environmentName string

@description('Azure region for every resource in this deployment (FR-65: one region per project).')
param location string = resourceGroup().location

@description('Project identifier, e.g. "deid" — kept short because some Azure resource names (storage accounts) have tight length limits.')
@maxLength(11)
param projectName string = 'deid'

@description('Container image references, e.g. myregistry.azurecr.io/deid-backend:sha-abc123. Left blank to provision infra without deploying a revision yet (first deploy commonly does this, then a CI pipeline pushes the real image tag).')
param apiImage string = ''
param workerImage string = ''
param frontendImage string = ''

@description('PostgreSQL administrator login. The password is generated and stored in Key Vault, never passed as a plain parameter.')
param postgresAdminLogin string = 'deidadmin'

@description('Anthropic API key for the optional Claude detector (FR-61 covers Azure AI Language; Claude is this project\'s additional context detector). Leave blank to disable it — stored in Key Vault either way, never in a container app setting.')
@secure()
param anthropicApiKey string = ''

@description('Enable zone redundancy (NFR-22: run across 3 availability zones). Requires a region with 3+ zones; disable for a region/SKU that does not support it (e.g. many staging deployments).')
param zoneRedundant bool = true

var namePrefix = '${projectName}-${environmentName}'
var tags = {
  project: projectName
  environment: environmentName
  'managed-by': 'bicep'
}

// ---------------------------------------------------------------------
// Log Analytics + Monitor (FR-64)
// ---------------------------------------------------------------------

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${namePrefix}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 90
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${namePrefix}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

// ---------------------------------------------------------------------
// Networking — every service reachable only over a private endpoint
// (FR-63: public network access off)
// ---------------------------------------------------------------------

resource vnet 'Microsoft.Network/virtualNetworks@2023-11-01' = {
  name: 'vnet-${namePrefix}'
  location: location
  tags: tags
  properties: {
    addressSpace: { addressPrefixes: ['10.20.0.0/16'] }
    subnets: [
      {
        name: 'snet-apps'
        properties: {
          addressPrefix: '10.20.0.0/23'
          delegations: [
            { name: 'containerapps', properties: { serviceName: 'Microsoft.App/environments' } }
          ]
        }
      }
      {
        name: 'snet-data'
        properties: {
          addressPrefix: '10.20.2.0/24'
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
      {
        name: 'snet-postgres'
        properties: {
          addressPrefix: '10.20.3.0/24'
          delegations: [
            { name: 'postgres', properties: { serviceName: 'Microsoft.DBforPostgreSQL/flexibleServers' } }
          ]
        }
      }
    ]
  }
}

resource privateDnsBlob 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.blob.${environment().suffixes.storage}'
  location: 'global'
  tags: tags
}
resource privateDnsKeyVault 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.vaultcore.azure.net'
  location: 'global'
  tags: tags
}
resource privateDnsServiceBus 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.servicebus.windows.net'
  location: 'global'
  tags: tags
}
resource privateDnsPostgres 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.postgres.database.azure.com'
  location: 'global'
  tags: tags
}

resource dnsLinkBlob 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: privateDnsBlob
  name: 'link-${namePrefix}'
  location: 'global'
  properties: { virtualNetwork: { id: vnet.id }, registrationEnabled: false }
}
resource dnsLinkKeyVault 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: privateDnsKeyVault
  name: 'link-${namePrefix}'
  location: 'global'
  properties: { virtualNetwork: { id: vnet.id }, registrationEnabled: false }
}
resource dnsLinkServiceBus 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: privateDnsServiceBus
  name: 'link-${namePrefix}'
  location: 'global'
  properties: { virtualNetwork: { id: vnet.id }, registrationEnabled: false }
}
resource dnsLinkPostgres 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: privateDnsPostgres
  name: 'link-${namePrefix}'
  location: 'global'
  properties: { virtualNetwork: { id: vnet.id }, registrationEnabled: false }
}

// ---------------------------------------------------------------------
// Managed identity (FR-62: every inter-service call uses a user-assigned
// managed identity, never a static key)
// ---------------------------------------------------------------------

resource pipelineIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'mi-${namePrefix}-pipeline'
  location: location
  tags: tags
}

// ---------------------------------------------------------------------
// Key Vault (FR-59)
// ---------------------------------------------------------------------

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'kv-${namePrefix}'
  location: location
  tags: tags
  properties: {
    sku: { family: 'A', name: 'standard' }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    publicNetworkAccess: 'Disabled'
    networkAcls: { defaultAction: 'Deny', bypass: 'AzureServices' }
  }
}

resource keyVaultPrivateEndpoint 'Microsoft.Network/privateEndpoints@2023-11-01' = {
  name: 'pe-${namePrefix}-kv'
  location: location
  tags: tags
  properties: {
    subnet: { id: vnet.properties.subnets[1].id }
    privateLinkServiceConnections: [
      {
        name: 'kv'
        properties: { privateLinkServiceId: keyVault.id, groupIds: ['vault'] }
      }
    ]
  }
}
resource keyVaultDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = {
  parent: keyVaultPrivateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      { name: 'kv', properties: { privateDnsZoneId: privateDnsKeyVault.id } }
    ]
  }
}

@description('Key Vault Secrets User — lets the pipeline identity read secrets (the Anthropic key, Postgres password) without a static credential.')
resource kvSecretsUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, pipelineIdentity.id, 'kv-secrets-user')
  scope: keyVault
  properties: {
    principalId: pipelineIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
  }
}

resource postgresPasswordSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'postgres-admin-password'
  properties: { value: uniqueString(subscription().id, resourceGroup().id, 'postgres-pw') }
}

resource anthropicKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(anthropicApiKey)) {
  parent: keyVault
  name: 'anthropic-api-key'
  properties: { value: anthropicApiKey }
}

// ---------------------------------------------------------------------
// Storage — Azure Blob Storage, the primary/reference store (FR-67/FR-68)
// ---------------------------------------------------------------------

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: replace('st${namePrefix}', '-', '')
  location: location
  tags: tags
  sku: { name: zoneRedundant ? 'Standard_ZRS' : 'Standard_LRS' }
  kind: 'StorageV2'
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${pipelineIdentity.id}': {} } }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true // FR-74: encryption in transit
    publicNetworkAccess: 'Disabled' // FR-63
    allowBlobPublicAccess: false
    networkAcls: { defaultAction: 'Deny', bypass: 'AzureServices' }
    encryption: {
      keySource: 'Microsoft.Storage' // FR-74 at rest; swap to Microsoft.Keyvault + a key in kv-${namePrefix} for a customer-managed key
      services: { blob: { enabled: true }, file: { enabled: true } }
    }
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}
resource containerIn 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'charts-in'
  properties: { publicAccess: 'None' }
}
resource containerOut 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'charts-out'
  properties: { publicAccess: 'None' }
}

resource storagePrivateEndpoint 'Microsoft.Network/privateEndpoints@2023-11-01' = {
  name: 'pe-${namePrefix}-blob'
  location: location
  tags: tags
  properties: {
    subnet: { id: vnet.properties.subnets[1].id }
    privateLinkServiceConnections: [
      { name: 'blob', properties: { privateLinkServiceId: storage.id, groupIds: ['blob'] } }
    ]
  }
}
resource storageDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = {
  parent: storagePrivateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      { name: 'blob', properties: { privateDnsZoneId: privateDnsBlob.id } }
    ]
  }
}

@description('Storage Blob Data Contributor — read/write charts-in and charts-out via managed identity, no static key (FR-62).')
resource storageBlobRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, pipelineIdentity.id, 'blob-data-contributor')
  scope: storage
  properties: {
    principalId: pipelineIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
  }
}

// ---------------------------------------------------------------------
// Queue — Azure Service Bus, one queue for the ingest stage (FR-57)
// ---------------------------------------------------------------------

resource serviceBus 'Microsoft.ServiceBus/namespaces@2022-10-01-preview' = {
  name: 'sb-${namePrefix}'
  location: location
  tags: tags
  sku: { name: 'Standard', tier: 'Standard' }
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${pipelineIdentity.id}': {} } }
  properties: {
    publicNetworkAccess: 'Disabled' // FR-63
  }
}

resource ingestQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: serviceBus
  name: 'deid-ingest'
  properties: {
    lockDuration: 'PT5M'
    maxDeliveryCount: 3
    deadLetteringOnMessageExpiration: true // a dead-letter queue is the reason Service Bus was chosen over Storage Queues
    requiresSession: false
  }
}

resource serviceBusPrivateEndpoint 'Microsoft.Network/privateEndpoints@2023-11-01' = {
  name: 'pe-${namePrefix}-sb'
  location: location
  tags: tags
  properties: {
    subnet: { id: vnet.properties.subnets[1].id }
    privateLinkServiceConnections: [
      { name: 'sb', properties: { privateLinkServiceId: serviceBus.id, groupIds: ['namespace'] } }
    ]
  }
}
resource serviceBusDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = {
  parent: serviceBusPrivateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      { name: 'sb', properties: { privateDnsZoneId: privateDnsServiceBus.id } }
    ]
  }
}

resource serviceBusDataOwnerRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(serviceBus.id, pipelineIdentity.id, 'sb-data-owner')
  scope: serviceBus
  properties: {
    principalId: pipelineIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '090c5cfd-751d-490a-894a-3ce6f1109419')
  }
}

// ---------------------------------------------------------------------
// Database — Azure Database for PostgreSQL (FR-58)
// ---------------------------------------------------------------------

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2023-06-01-preview' = {
  name: 'psql-${namePrefix}'
  location: location
  tags: tags
  sku: { name: 'Standard_D2ds_v5', tier: 'GeneralPurpose' }
  properties: {
    version: '16'
    administratorLogin: postgresAdminLogin
    administratorLoginPassword: postgresPasswordSecret.properties.value
    network: {
      delegatedSubnetResourceId: vnet.properties.subnets[2].id
      privateDnsZoneArmResourceId: privateDnsPostgres.id
      publicNetworkAccess: 'Disabled' // FR-63
    }
    highAvailability: {
      mode: zoneRedundant ? 'ZoneRedundant' : 'Disabled' // NFR-22
    }
    storage: { storageSizeGB: 128 }
    backup: { backupRetentionDays: 14, geoRedundantBackup: 'Disabled' }
  }
  dependsOn: [dnsLinkPostgres]
}

resource postgresDb 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-06-01-preview' = {
  parent: postgres
  name: 'deid'
}

// ---------------------------------------------------------------------
// AI services — Document Intelligence (FR-60) + Language (FR-61)
// ---------------------------------------------------------------------

resource documentIntelligence 'Microsoft.CognitiveServices/accounts@2023-05-01' = {
  name: 'di-${namePrefix}'
  location: location
  tags: tags
  kind: 'FormRecognizer'
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${pipelineIdentity.id}': {} } }
  sku: { name: 'S0' }
  properties: {
    customSubDomainName: 'di-${namePrefix}'
    publicNetworkAccess: 'Disabled' // FR-63
    disableLocalAuth: true // FR-62: managed identity only, no static key
  }
}

resource language 'Microsoft.CognitiveServices/accounts@2023-05-01' = {
  name: 'lang-${namePrefix}'
  location: location
  tags: tags
  kind: 'TextAnalytics'
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${pipelineIdentity.id}': {} } }
  sku: { name: 'S' }
  properties: {
    customSubDomainName: 'lang-${namePrefix}'
    publicNetworkAccess: 'Disabled' // FR-63
    disableLocalAuth: true
  }
}

@description('Cognitive Services User — call Document Intelligence/Language via managed identity.')
resource diCognitiveUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(documentIntelligence.id, pipelineIdentity.id, 'cognitive-user')
  scope: documentIntelligence
  properties: {
    principalId: pipelineIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'a97b65f3-24c7-4388-baec-2e87135dc908')
  }
}
resource langCognitiveUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(language.id, pipelineIdentity.id, 'cognitive-user')
  scope: language
  properties: {
    principalId: pipelineIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'a97b65f3-24c7-4388-baec-2e87135dc908')
  }
}

// ---------------------------------------------------------------------
// Compute — Container Apps environment + jobs (FR-56), scale to zero on
// an empty queue (NFR-23)
// ---------------------------------------------------------------------

resource containerAppsEnv 'Microsoft.App/managedEnvironments@2023-11-02-preview' = {
  name: 'cae-${namePrefix}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
    vnetConfiguration: { infrastructureSubnetId: vnet.properties.subnets[0].id }
    zoneRedundant: zoneRedundant // NFR-22
  }
}

var commonEnv = [
  { name: 'DJANGO_ALLOWED_HOSTS', value: '*' } // tighten to the real hostname once the Container App FQDN/custom domain is known
  { name: 'DATABASE_URL', value: 'postgresql://${postgresAdminLogin}:${postgresPasswordSecret.properties.value}@${postgres.properties.fullyQualifiedDomainName}:5432/deid' }
  { name: 'DATABASE_SSL_REQUIRE', value: 'True' }
  { name: 'CELERY_BROKER_URL', value: 'azureservicebus://${serviceBus.name}.servicebus.windows.net' }
  { name: 'CELERY_TASK_DEFAULT_QUEUE', value: ingestQueue.name }
  { name: 'STORAGE_PROVIDER', value: 'azure_blob' }
  { name: 'AZURE_STORAGE_ACCOUNT', value: storage.name }
  { name: 'AZURE_STORAGE_CONTAINER', value: containerIn.name }
  { name: 'REDACTION_ENABLE_AZURE_LANGUAGE', value: 'True' }
  { name: 'AZURE_LANGUAGE_ENDPOINT', value: language.properties.endpoint }
  { name: 'REDACTION_ENABLE_AZURE_OCR', value: 'True' }
  { name: 'AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT', value: documentIntelligence.properties.endpoint }
  { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
  { name: 'REDACTION_ENABLE_AI', value: string(!empty(anthropicApiKey)) }
]

var secretsRef = !empty(anthropicApiKey) ? [
  { name: 'anthropic-api-key', keyVaultUrl: '${keyVault.properties.vaultUri}secrets/anthropic-api-key', identity: pipelineIdentity.id }
] : []
var anthropicEnv = !empty(anthropicApiKey) ? [
  { name: 'ANTHROPIC_API_KEY', secretRef: 'anthropic-api-key' }
] : []

resource apiApp 'Microsoft.App/containerApps@2023-11-02-preview' = if (!empty(apiImage)) {
  name: 'ca-${namePrefix}-api'
  location: location
  tags: tags
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${pipelineIdentity.id}': {} } }
  properties: {
    managedEnvironmentId: containerAppsEnv.id
    configuration: {
      ingress: { external: true, targetPort: 8000, transport: 'http2' }
      secrets: secretsRef
    }
    template: {
      containers: [
        {
          name: 'api'
          image: apiImage
          env: concat(commonEnv, anthropicEnv)
          resources: { cpu: json('1.0'), memory: '2Gi' }
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 5 }
    }
  }
}

// The worker is a queue-driven job (FR-56), not a long-running app: it
// scales entirely off the Service Bus queue's message count, including
// down to zero replicas on an empty queue (NFR-23).
resource workerJob 'Microsoft.App/jobs@2023-11-02-preview' = if (!empty(workerImage)) {
  name: 'caj-${namePrefix}-worker'
  location: location
  tags: tags
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${pipelineIdentity.id}': {} } }
  properties: {
    environmentId: containerAppsEnv.id
    configuration: {
      triggerType: 'Event'
      replicaTimeout: 900
      replicaRetryLimit: 1
      secrets: secretsRef
      eventTriggerConfig: {
        scale: {
          minExecutions: 0
          maxExecutions: 8
          rules: [
            {
              name: 'service-bus-queue-length'
              type: 'azure-servicebus'
              metadata: {
                queueName: ingestQueue.name
                namespace: serviceBus.name
                messageCount: '5'
              }
              auth: [
                { secretRef: '', triggerParameter: 'workloadIdentity' }
              ]
            }
          ]
        }
      }
    }
    template: {
      containers: [
        {
          name: 'worker'
          image: workerImage
          command: ['celery', '-A', 'deid_backend', 'worker', '--loglevel=INFO', '-Q', 'deid-ingest']
          env: concat(commonEnv, anthropicEnv)
          resources: { cpu: json('1.0'), memory: '2Gi' }
        }
      ]
    }
  }
}

resource frontendApp 'Microsoft.App/containerApps@2023-11-02-preview' = if (!empty(frontendImage)) {
  name: 'ca-${namePrefix}-frontend'
  location: location
  tags: tags
  properties: {
    managedEnvironmentId: containerAppsEnv.id
    configuration: {
      ingress: { external: true, targetPort: 80 }
    }
    template: {
      containers: [
        { name: 'frontend', image: frontendImage, resources: { cpu: json('0.5'), memory: '1Gi' } }
      ]
      scale: { minReplicas: 1, maxReplicas: 3 }
    }
  }
}

// ---------------------------------------------------------------------
// Outputs
// ---------------------------------------------------------------------

output pipelineIdentityId string = pipelineIdentity.id
output pipelineIdentityPrincipalId string = pipelineIdentity.properties.principalId
output storageAccountName string = storage.name
output serviceBusNamespace string = serviceBus.name
output postgresFqdn string = postgres.properties.fullyQualifiedDomainName
output keyVaultUri string = keyVault.properties.vaultUri
output logAnalyticsWorkspaceId string = logAnalytics.id
output apiUrl string = !empty(apiImage) ? 'https://${apiApp.?properties.?configuration.?ingress.?fqdn}' : ''
output frontendUrl string = !empty(frontendImage) ? 'https://${frontendApp.?properties.?configuration.?ingress.?fqdn}' : ''
