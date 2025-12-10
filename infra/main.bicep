@description('Azure region for this deployment.')
param location string = resourceGroup().location

@description('Short environment name used to create unique resource names (e.g. dev, prod).')
param environmentName string

@description('Base service name used for resource naming.')
param serviceName string = 'boto'

@description('App Service plan SKU name (e.g. B1, P1v3).')
param appServiceSkuName string = 'B1'

@description('App Service plan SKU tier (e.g. Basic, PremiumV3). Must align with the SKU name.')
param appServiceSkuTier string = 'Basic'

@description('Custom domain to bind to the Web App (e.g. boto.infoamazonia.org). Leave blank to skip.')
param customDomainName string = ''

@description('Application settings (key/value) mirrored from the project .env files.')
param appSettings object = {}

@description('Service identifier used by azd for tagging resources.')
param azdServiceName string = 'infoamazonia-boto'

var appServicePlanName = '${serviceName}-${environmentName}-plan'
var webAppName = '${serviceName}-${environmentName}-app'

module web './resources.bicep' = {
	name: 'web-app'
	params: {
		location: location
		appServicePlanName: appServicePlanName
		appServiceSkuName: appServiceSkuName
		appServiceSkuTier: appServiceSkuTier
		webAppName: webAppName
		appSettings: appSettings
		customDomainName: customDomainName
		azdServiceName: azdServiceName
		azdEnvironmentName: environmentName
	}
}

output webAppName string = webAppName
output webAppDefaultHostname string = web.outputs.webAppDefaultHostname
output webAppHostname string = web.outputs.webAppHostname
