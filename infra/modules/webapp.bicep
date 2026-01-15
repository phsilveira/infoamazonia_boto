@description('Azure region for the App Service resources.')
param location string

@description('Name of the App Service plan.')
param appServicePlanName string

@description('SKU name for the App Service plan (e.g. B1, P1v3).')
param appServiceSkuName string

@description('SKU tier for the App Service plan (e.g. Basic, PremiumV3).')
param appServiceSkuTier string

@description('Name of the Web App resource.')
param webAppName string

@description('When no container image is provided, use this built-in runtime (format: RUNTIME|VERSION).')
param linuxFxVersion string = 'PYTHON|3.11'

@description('Container image reference (registry/repo:tag). Leave empty to run on the built-in runtime.')
param containerImage string = ''

@description('Container registry server URL (e.g., myregistry.azurecr.io). Required when pulling from a private registry.')
param containerRegistryServer string = ''

@description('Container registry username.')
param containerRegistryUsername string = ''

@secure()
@description('Container registry password or access token.')
param containerRegistryPassword string = ''

@description('Combined application settings (name/value pairs) to apply to the Web App.')
param appSettings object = {}

@description('Optional custom domain to bind to the Web App.')
param customDomainName string = ''

@description('Startup command override. Leave blank to use the image entrypoint.')
param startupCommand string = ''

@description('Ensure the Web App stays warm. Recommended for API workloads.')
param alwaysOn bool = true

@description('Tags applied to the App Service plan (environment-level).')
param planTags object = {}

@description('Tags applied to the Web App (service-level).')
param siteTags object = {}

var resolvedLinuxFxVersion = empty(containerImage) ? linuxFxVersion : format('DOCKER|{0}', containerImage)

var baseAppSettings = {
  SCM_DO_BUILD_DURING_DEPLOYMENT: empty(containerImage) ? '1' : '0'
  WEBSITES_PORT: '8000'
  WEBSITES_ENABLE_APP_SERVICE_STORAGE: 'false'
}

var containerRegistrySettings = empty(containerRegistryServer) ? {} : {
  DOCKER_REGISTRY_SERVER_URL: containerRegistryServer
  DOCKER_REGISTRY_SERVER_USERNAME: containerRegistryUsername
  DOCKER_REGISTRY_SERVER_PASSWORD: containerRegistryPassword
}

var resolvedAppSettings = union(baseAppSettings, containerRegistrySettings, appSettings)

var appSettingsList = [for setting in items(resolvedAppSettings): {
  name: setting.key
  value: string(setting.value)
}]

resource appServicePlan 'Microsoft.Web/serverfarms@2023-01-01' = {
  name: appServicePlanName
  location: location
  tags: planTags
  sku: {
    name: appServiceSkuName
    tier: appServiceSkuTier
  }
  kind: 'linux'
  properties: {
    reserved: true
    perSiteScaling: false
  }
}

resource webApp 'Microsoft.Web/sites@2023-01-01' = {
  name: webAppName
  location: location
  tags: siteTags
  kind: 'app,linux'
  properties: {
    serverFarmId: appServicePlan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: resolvedLinuxFxVersion
      appSettings: appSettingsList
      alwaysOn: alwaysOn
      ftpsState: 'FtpsOnly'
      appCommandLine: startupCommand
    }
  }
}

resource domainBinding 'Microsoft.Web/sites/hostNameBindings@2023-01-01' = if (!empty(customDomainName)) {
  parent: webApp
  name: customDomainName
  properties: {
    hostNameType: 'Verified'
    customHostNameDnsRecordType: 'CName'
  }
}

output planId string = appServicePlan.id
output webAppName string = webApp.name
output defaultHostname string = webApp.properties.defaultHostName
output hostname string = empty(customDomainName) ? webApp.properties.defaultHostName : customDomainName
