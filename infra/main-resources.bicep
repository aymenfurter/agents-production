@description('Name of the environment')
param environmentName string

@description('Primary location for all resources')
param location string

@description('Principal ID for role assignments')
param principalId string = ''

var abbrs = {
  applicationInsights: 'appi-'
  containerAppsEnvironment: 'cae-'
  containerRegistry: 'cr'
  keyVault: 'kv-'
  logAnalyticsWorkspace: 'log-'
  storageAccount: 'st'
}

var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var tags = { 'azd-env-name': environmentName }

// Monitoring resources
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2021-12-01-preview' = {
  name: '${abbrs.logAnalyticsWorkspace}${resourceToken}'
  location: location
  tags: tags
  properties: {
    retentionInDays: 30
    sku: {
      name: 'PerGB2018'
    }
  }
}

resource applicationInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${abbrs.applicationInsights}${resourceToken}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
    IngestionMode: 'LogAnalytics'
  }
}

// Container Registry
resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-01-01-preview' = {
  name: '${abbrs.containerRegistry}${resourceToken}'
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: true
  }
}

// Storage Account for AI Foundry Hub
resource storageAccount 'Microsoft.Storage/storageAccounts@2022-09-01' = {
  name: '${abbrs.storageAccount}${resourceToken}'
  location: location
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
  }
}

// Key Vault for AI Foundry Hub
resource keyVault 'Microsoft.KeyVault/vaults@2022-07-01' = {
  name: '${abbrs.keyVault}${resourceToken}'
  location: location
  tags: tags
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
  }
}

// Content Safety Service
resource contentSafety 'Microsoft.CognitiveServices/accounts@2023-05-01' = {
  name: 'contentsafety-${resourceToken}'
  location: location
  tags: tags
  kind: 'ContentSafety'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: 'contentsafety-${resourceToken}'
    publicNetworkAccess: 'Enabled'
  }
}

// AI Foundry Resource Deployment (CognitiveServices account with AIServices)
resource aiFoundryResource 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: 'aifoundry-sweden-${resourceToken}'
  location: location
  tags: tags
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    customSubDomainName: 'aifoundry-sweden-${resourceToken}'
    publicNetworkAccess: 'Enabled'
    allowProjectManagement: true
  }
}

// AI Project under AI Foundry Resource
resource aiProject 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  name: 'default-project'
  parent: aiFoundryResource
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {}
}

// Application Insights connection for AI Foundry Resource
resource aiFoundryAppInsightsConnection 'Microsoft.CognitiveServices/accounts/connections@2025-04-01-preview' = {
  name: 'appinsights-connection'
  parent: aiFoundryResource
  properties: {
    category: 'AppInsights'
    target: applicationInsights.id
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: {
      key: applicationInsights.properties.ConnectionString
    }
    metadata: {
      ApiType: 'Azure'
      ResourceId: applicationInsights.id
    }
  }
}

// Azure OpenAI connection for AI Foundry Resource (self-referencing for agent operations)
resource aiFoundryAOAIConnection 'Microsoft.CognitiveServices/accounts/connections@2025-04-01-preview' = {
  name: 'aoai-connection'
  parent: aiFoundryResource
  properties: {
    category: 'AzureOpenAI'
    authType: 'AAD'
    isSharedToAll: true
    target: aiFoundryResource.properties.endpoints['OpenAI Language Model Instance API']
    metadata: {
      ApiType: 'azure'
      ResourceId: aiFoundryResource.id
    }
  }
}

// Storage account connection for AI Foundry Resource
resource aiFoundryStorageConnection 'Microsoft.CognitiveServices/accounts/connections@2025-04-01-preview' = {
  name: 'storage-connection'
  parent: aiFoundryResource
  properties: {
    category: 'AzureStorageAccount'
    target: storageAccount.id
    authType: 'AAD'
    isSharedToAll: true
    metadata: {
      ApiType: 'Azure'
      ResourceId: storageAccount.id
    }
  }
}

// AI Services for Hub
resource aiServicesHub 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: 'aiservices-hub-${resourceToken}'
  location: location
  tags: tags
  sku: {
    name: 'S0'
  }
  kind: 'AIServices'
  properties: {
    customSubDomainName: 'aiservices-hub-${resourceToken}'
    publicNetworkAccess: 'Enabled'
  }
}

// AI Foundry Hub - Keep containerRegistry reference
resource aiHub 'Microsoft.MachineLearningServices/workspaces@2024-10-01' = {
  name: 'aifoundry-hub-${resourceToken}'
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  kind: 'hub'
  properties: {
    friendlyName: 'AI Foundry Hub ${environmentName}'
    description: 'AI Foundry Hub for ${environmentName}'
    keyVault: keyVault.id
    storageAccount: storageAccount.id
    applicationInsights: applicationInsights.id
    containerRegistry: containerRegistry.id
  }

  resource aiServicesConnection 'connections@2024-01-01-preview' = {
    name: 'aiservices-connection'
    properties: {
      category: 'AzureOpenAI'
      target: aiServicesHub.properties.endpoint
      authType: 'ApiKey'
      isSharedToAll: true
      credentials: {
        key: aiServicesHub.listKeys().key1
      }
      metadata: {
        ApiType: 'Azure'
        ResourceId: aiServicesHub.id
      }
    }
  }
}

// AI Project in Hub
resource aiHubProject 'Microsoft.MachineLearningServices/workspaces@2024-10-01' = {
  name: 'aifoundry-project-${resourceToken}'
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  kind: 'project'
  properties: {
    friendlyName: 'AI Foundry Project ${environmentName}'
    description: 'AI Foundry Project for ${environmentName}'
    hubResourceId: aiHub.id
  }
}

// Container Apps Environment
resource containerAppsEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${abbrs.containerAppsEnvironment}${resourceToken}'
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
  }
}

// Container App - Update with specific image tag
resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'agents-production-${resourceToken}'
  location: location
  tags: union(tags, { 'azd-service-name': 'agents-production' })
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerAppsEnvironment.id
    configuration: {
      ingress: {
        external: true
        targetPort: 7860
        transport: 'http'
      }
      secrets: [
        {
          name: 'azure-ml-api-key'
          value: 'foobar' // Static placeholder for GPT-2 endpoint
        }
        {
          name: 'eval-model-api-key'
          value: aiFoundryResource.listKeys().key1
        }
        {
          name: 'content-safety-key'
          value: contentSafety.listKeys().key1
        }
        {
          name: 'openai-agents-api-key'
          value: aiFoundryResource.listKeys().key1
        }
        {
          name: 'appinsights-connection-string'
          #disable-next-line use-secure-value-for-secure-inputs
          value: applicationInsights.properties.ConnectionString
        }
      ]
    }
    template: {
      containers: [
        {
          image: 'ghcr.io/aymenfurter/agents-in-production:main-35f98e0'  // Updated to specific tag
          name: 'agents-production'
          resources: {
            cpu: json('1.0')
            memory: '2.0Gi'
          }
          env: [
            {
              name: 'PROJECT_ENDPOINT'
              value: '${aiFoundryResource.properties.endpoint}api/projects/default-project'
            }
            {
              name: 'MODEL_DEPLOYMENT_NAME'
              value: 'gpt-4.1'
            }
            {
              name: 'MODEL_DEPLOYMENT_NAME_ALT'
              value: 'gpt-35-turbo'
            }
            {
              name: 'AZURE_ML_API_KEY'
              secretRef: 'azure-ml-api-key'
            }
            {
              name: 'AZURE_ML_ENDPOINT'
              value: 'https://your-gpt2-endpoint.inference.ml.azure.com/score'
            }
            {
              name: 'EVAL_MODEL_ENDPOINT'
              value: '${aiFoundryResource.properties.endpoint}/'
            }
            {
              name: 'EVAL_MODEL_API_KEY'
              secretRef: 'eval-model-api-key'
            }
            {
              name: 'EVAL_MODEL_DEPLOYMENT'
              value: 'gpt-4.1'
            }
            {
              name: 'AZURE_SUBSCRIPTION_ID'
              value: subscription().subscriptionId
            }
            {
              name: 'AZURE_RESOURCE_GROUP'
              value: resourceGroup().name
            }
            {
              name: 'AZURE_PROJECT_NAME'
              value: aiHubProject.name
            }
            {
              name: 'AZURE_TENANT_ID'
              value: subscription().tenantId
            }
            {
              name: 'CONTENT_SAFETY_ENDPOINT'
              value: contentSafety.properties.endpoint
            }
            {
              name: 'CONTENT_SAFETY_REGION'
              value: location
            }
            {
              name: 'CONTENT_SAFETY_KEY'
              secretRef: 'content-safety-key'
            }
            {
              name: 'OPENAI_AGENTS_ENDPOINT'
              value: '${aiFoundryResource.properties.endpoint}/'
            }
            {
              name: 'OPENAI_AGENTS_API_KEY'
              secretRef: 'openai-agents-api-key'
            }
            {
              name: 'OPENAI_AGENTS_DEPLOYMENT'
              value: 'gpt-5'
            }
            {
              name: 'OPENAI_AGENTS_API_VERSION'
              value: '2025-04-01-preview'
            }
            {
              name: 'OPENAI_AGENTS_DISABLE_TRACING'
              value: '1'
            }
            {
              name: 'OTEL_SERVICE_NAME'
              value: 'ContosoCareAgent'
            }
            {
              name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
              secretRef: 'appinsights-connection-string'
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

// Role Assignments for Container App Identity
// Using static GUID generation based on resource names

// Azure AI Developer role for agent operations
resource containerAppAzureAIDeveloperRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(subscription().id, resourceGroup().id, 'agents-production-${resourceToken}', '64702f94-c441-49e6-a78b-ef80e0188fee')
  properties: {
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: resourceId('Microsoft.Authorization/roleDefinitions', '64702f94-c441-49e6-a78b-ef80e0188fee')
  }
}

// Cognitive Services User role for accessing AI Services
resource containerAppCognitiveServicesUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(subscription().id, resourceGroup().id, 'agents-production-${resourceToken}', 'a97b65f3-24c7-4388-baec-2e87135dc908')
  properties: {
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: resourceId('Microsoft.Authorization/roleDefinitions', 'a97b65f3-24c7-4388-baec-2e87135dc908')
  }
}

// Cognitive Services OpenAI User role for OpenAI operations including agents
resource containerAppCognitiveServicesOpenAIUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(subscription().id, resourceGroup().id, 'agents-production-${resourceToken}', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')
  properties: {
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: resourceId('Microsoft.Authorization/roleDefinitions', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')
  }
}

// Monitoring Metrics Contributor role for Application Insights
resource containerAppMonitoringMetricsContributorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: applicationInsights
  name: guid(subscription().id, resourceGroup().id, 'agents-production-${resourceToken}', 'appi', '749f88d5-cbae-40b8-bcfc-e573ddc772fa')
  properties: {
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: resourceId('Microsoft.Authorization/roleDefinitions', '749f88d5-cbae-40b8-bcfc-e573ddc772fa')
  }
}

// Storage Blob Data Contributor role for AI Foundry storage operations
resource containerAppStorageBlobDataContributorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storageAccount
  name: guid(subscription().id, resourceGroup().id, 'agents-production-${resourceToken}', 'storage', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
  properties: {
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: resourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
  }
}

// Key Vault Secrets User role for accessing Key Vault secrets
resource containerAppKeyVaultSecretsUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: keyVault
  name: guid(subscription().id, resourceGroup().id, 'agents-production-${resourceToken}', 'keyvault', '4633458b-17de-408a-b874-0445c86b69e6')
  properties: {
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: resourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
  }
}

// Role Assignments for AI Foundry Resource principal to access Storage
resource aiFoundryStorageRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storageAccount
  name: guid(subscription().id, resourceGroup().id, 'aifoundry-sweden-${resourceToken}', 'storage', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
  properties: {
    principalId: aiFoundryResource.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: resourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe') // Storage Blob Data Contributor
  }
}

// Role Assignment for AI Project principal to access Storage
resource aiProjectStorageRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storageAccount
  name: guid(subscription().id, resourceGroup().id, 'aifoundry-project-${resourceToken}', 'storage', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
  properties: {
    principalId: aiProject.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: resourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe') // Storage Blob Data Contributor
  }
}

// Add role assignments for principalId parameter if provided
resource userAzureAIDeveloperRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(subscription().id, resourceGroup().id, principalId, '64702f94-c441-49e6-a78b-ef80e0188fee')
  properties: {
    principalId: principalId
    principalType: 'User'
    roleDefinitionId: resourceId('Microsoft.Authorization/roleDefinitions', '64702f94-c441-49e6-a78b-ef80e0188fee')
  }
}

// Outputs
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = containerRegistry.properties.loginServer
output AZURE_CONTAINER_APP_ENVIRONMENT_NAME string = containerAppsEnvironment.name
output AZURE_CONTAINER_APP_NAME string = containerApp.name
output SERVICE_AGENTS_PRODUCTION_URI string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output AZURE_TENANT_ID string = subscription().tenantId
output AZURE_SUBSCRIPTION_ID string = subscription().subscriptionId
output CONTAINER_APP_IDENTITY_PRINCIPAL_ID string = containerApp.identity.principalId
