@description('Azure region for the resources.')
param location string

@description('Name of the App Service plan to create.')
param appServicePlanName string

@description('SKU name for the App Service plan (e.g. B1, P1v3).')
param appServiceSkuName string

@description('SKU tier for the App Service plan (e.g. Basic, PremiumV3).')
param appServiceSkuTier string

@description('Name of the Web App to deploy the FastAPI service.')
param webAppName string

@description('Linux runtime stack for the Web App (format: RUNTIME|VERSION).')
param linuxFxVersion string = 'PYTHON|3.11'

@description('Application settings to inject (mirrors the contents of .env).')
param appSettings object = {}

@description('Optional custom domain (e.g. boto.infoamazonia.org). Leave blank to skip binding.')
param customDomainName string = ''

@description('Azure Developer CLI service name used for resource tagging (matches azure.yaml service name).')
param azdServiceName string

@description('Azure Developer CLI environment name used for resource tagging.')
param azdEnvironmentName string

@description('Startup command that launches the FastAPI app inside App Service.')
param startupCommand string = 'python main.py'


var baseAppSettings = [
	{
		name: 'SCM_DO_BUILD_DURING_DEPLOYMENT'
		value: '1'
	}
	{
		name: 'WEBSITES_ENABLE_APP_SERVICE_STORAGE'
		value: 'false'
	}
	{
		name: 'WEBSITES_PORT'
		value: '8000'
	}
	{
		name: 'PORT'
		value: '8000'
	}
]

var userAppSettings = [for setting in items(appSettings): {
	name: setting.key
	value: string(setting.value)
}]

var azdEnvTags = {
	'azd-env-name': azdEnvironmentName
}

var azdServiceTags = union(azdEnvTags, {
	'azd-service-name': azdServiceName
})

resource appServicePlan 'Microsoft.Web/serverfarms@2023-01-01' = {
	name: appServicePlanName
	location: location
	tags: azdEnvTags
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
	tags: azdServiceTags
	kind: 'app,linux'
	properties: {
		serverFarmId: appServicePlan.id
		httpsOnly: true
		siteConfig: {
			linuxFxVersion: linuxFxVersion
			alwaysOn: true
			ftpsState: 'FtpsOnly'
			appCommandLine: startupCommand
			appSettings: concat(baseAppSettings, userAppSettings)
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

output webAppName string = webApp.name
output webAppDefaultHostname string = webApp.properties.defaultHostName
output webAppHostname string = empty(customDomainName) ? webApp.properties.defaultHostName : customDomainName
