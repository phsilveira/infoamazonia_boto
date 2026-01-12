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

@description('Name of the Azure Cache for Redis instance.')
param redisName string

@description('Redis SKU name (Basic, Standard, Premium).')
param redisSkuName string

@description('Redis SKU family (C for Basic/Standard, P for Premium).')
param redisSkuFamily string

@description('Redis capacity (0 = 250MB, 1 = 1GB, etc.).')
param redisCapacity int

@description('Whether to enable the non-SSL Redis port (6379). Defaults to false to require TLS.')
param redisEnableNonSslPort bool

@description('Minimum TLS version for Redis (e.g., 1.2).')
param redisMinimumTlsVersion string

@description('Name of the Azure Database for PostgreSQL Flexible Server instance.')
param postgresServerName string

@description('Administrator username for PostgreSQL Flexible Server.')
param postgresAdminUsername string

@secure()
@description('Administrator password for PostgreSQL Flexible Server.')
param postgresAdminPassword string

@description('Default PostgreSQL database name to create.')
param postgresDatabaseName string

@description('PostgreSQL major version (e.g., 16, 15).')
param postgresVersion string

@description('SKU name for PostgreSQL Flexible Server (e.g., Standard_B1ms).')
param postgresSkuName string

@description('SKU tier for PostgreSQL Flexible Server (e.g., Burstable, GeneralPurpose).')
param postgresSkuTier string

@description('Storage size in GB for PostgreSQL Flexible Server.')
param postgresStorageSizeGB int

@description('Backup retention days for PostgreSQL Flexible Server.')
param postgresBackupRetentionDays int


var baseAppSettings = [
	{
		name: 'SCM_DO_BUILD_DURING_DEPLOYMENT'
		value: '1'
	}
	{
		name: 'WEBSITES_PORT'
		value: '8000'
	}
	{
		name: 'WEBSITES_ENABLE_APP_SERVICE_STORAGE'
		value: 'false'
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

var redisApiVersion = '2023-08-01'

var redisPortSetting = redisEnableNonSslPort ? '6379' : '6380'

var redisUseTlsSetting = redisEnableNonSslPort ? 'false' : 'true'

var postgresHostName = format('{0}.postgres.database.azure.com', postgresServerName)

var postgresConnectionString = format('postgresql+psycopg://{0}:{1}@{2}:5432/{3}?sslmode=require', postgresAdminUsername, uriComponent(postgresAdminPassword), postgresHostName, postgresDatabaseName)

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

resource redisCache 'Microsoft.Cache/Redis@2023-08-01' = {
	name: redisName
	location: location
	tags: azdEnvTags
	properties: {
		sku: {
			name: redisSkuName
			family: redisSkuFamily
			capacity: redisCapacity
		}
		enableNonSslPort: redisEnableNonSslPort
		minimumTlsVersion: redisMinimumTlsVersion
		redisConfiguration: {
			'maxmemory-reserved': '10'
		}
	}
}

var redisKeys = listKeys(redisCache.id, redisApiVersion)

var managedRedisSettings = [
	{
		name: 'REDIS_HOST'
		value: redisCache.properties.hostName
	}
	{
		name: 'REDIS_PORT'
		value: redisPortSetting
	}
	{
		name: 'REDIS_PASSWORD'
		value: redisKeys.primaryKey
	}
	{
		name: 'REDIS_USE_TLS'
		value: redisUseTlsSetting
	}
]

resource postgresServer 'Microsoft.DBforPostgreSQL/flexibleServers@2022-12-01' = {
	name: postgresServerName
	location: location
	tags: azdEnvTags
	sku: {
		name: postgresSkuName
		tier: postgresSkuTier
	}
	properties: {
		administratorLogin: postgresAdminUsername
		administratorLoginPassword: postgresAdminPassword
		version: postgresVersion
		backup: {
			backupRetentionDays: postgresBackupRetentionDays
		}
		storage: {
			storageSizeGB: postgresStorageSizeGB
			autoGrow: 'Enabled'
		}
		network: {
			publicNetworkAccess: 'Enabled'
		}
		highAvailability: {
			mode: 'Disabled'
		}
	}
}

resource postgresDatabase 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2022-12-01' = {
	name: '${postgresServer.name}/${postgresDatabaseName}'
	properties: {}
}

resource postgresFirewallAllowAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2022-12-01' = {
	name: '${postgresServer.name}/allow-azure-services'
	properties: {
		startIpAddress: '0.0.0.0'
		endIpAddress: '0.0.0.0'
	}
}

var managedPostgresSettings = [
	{
		name: 'DATABASE_URL'
		value: postgresConnectionString
	}
	{
		name: 'PGHOST'
		value: postgresHostName
	}
	{
		name: 'PGPORT'
		value: '5432'
	}
	{
		name: 'PGUSER'
		value: format('{0}@{1}', postgresAdminUsername, postgresServerName)
	}
	{
		name: 'PGPASSWORD'
		value: postgresAdminPassword
	}
	{
		name: 'PGDATABASE'
		value: postgresDatabaseName
	}
]

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
			appSettings: concat(baseAppSettings, managedRedisSettings, managedPostgresSettings, userAppSettings)
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
output redisHostName string = redisCache.properties.hostName
output redisPort string = redisPortSetting
output redisPrimaryKey string = redisKeys.primaryKey
output postgresHostName string = postgresHostName
output postgresDatabaseName string = postgresDatabaseName
output postgresConnectionString string = postgresConnectionString
