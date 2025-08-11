targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the environment that can be used as part of naming resource convention')
param environmentName string

@minLength(1)
@description('Primary location for all resources')
param location string

@description('Id of the user or app to assign application roles')
param principalId string = ''

// Resource group
resource rg 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: 'rg-${environmentName}'
  location: location
}

module main 'main-resources.bicep' = {
  name: 'main-resources'
  scope: rg
  params: {
    environmentName: environmentName
    location: location
    principalId: principalId
  }
}

output AZURE_CONTAINER_APP_ENVIRONMENT_NAME string = main.outputs.AZURE_CONTAINER_APP_ENVIRONMENT_NAME
output AZURE_CONTAINER_APP_NAME string = main.outputs.AZURE_CONTAINER_APP_NAME
output SERVICE_AGENTS_PRODUCTION_URI string = main.outputs.SERVICE_AGENTS_PRODUCTION_URI
