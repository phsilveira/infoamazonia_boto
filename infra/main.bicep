@description('Azure region for this deployment.')
param location string = resourceGroup().location

@description('Short environment name used to create unique resource names (e.g. dev, prod).')
param environmentName string

@description('Base service name used for resource naming.')
param serviceName string = 'boto'

@description('Service identifier used by azd for tagging resources.')
param azdServiceName string = 'infoamazonia-boto'

@description('App Service plan SKU name (e.g. B1, P1v3).')
param appServiceSkuName string = 'B1'

@description('App Service plan SKU tier (e.g. Basic, PremiumV3). Must align with the SKU name.')
param appServiceSkuTier string = 'Basic'

@description('Optional custom domain for the Web App.')
param customDomainName string = ''

@description('Extra application settings merged into the deployment (mirrors .env contents).')
param appSettings object = {}

@description('Container image to run (registry/repository:tag). Leave blank to use the built-in Python runtime.')
param containerImage string = ''

@description('Container registry server URL (e.g., myregistry.azurecr.io). Required when using a private registry.')
param containerRegistryServer string = ''

@description('Container registry username.')
param containerRegistryUsername string = ''

@secure()
@description('Container registry password or access token.')
param containerRegistryPassword string = ''

@description('Startup command override for the App Service container.')
param startupCommand string = ''

@description('Redis SKU name (Basic, Standard, Premium).')
param redisSkuName string = 'Basic'

@description('Redis SKU family (C for Basic/Standard, P for Premium).')
param redisSkuFamily string = 'C'

@description('Redis capacity (0 = 250MB, 1 = 1GB, etc.).')
param redisCapacity int = 0

@description('Whether to enable the non-SSL Redis port (6379). Defaults to false to force TLS only.')
param redisEnableNonSslPort bool = false

@description('Minimum TLS version enforced on the Redis cache.')
param redisMinimumTlsVersion string = '1.2'

@description('PostgreSQL Flexible Server administrator username.')
param postgresAdminUsername string = 'boto_admin'

@secure()
@description('PostgreSQL Flexible Server administrator password.')
param postgresAdminPassword string

@description('Name of the default PostgreSQL database to create.')
param postgresDatabaseName string = 'infoamazonia'

@description('PostgreSQL major version for the Flexible Server.')
param postgresVersion string = '16'

@description('SKU name for PostgreSQL Flexible Server (e.g., Standard_B1ms).')
param postgresSkuName string = 'Standard_B1ms'

@description('SKU tier for PostgreSQL Flexible Server (e.g., Burstable, GeneralPurpose).')
param postgresSkuTier string = 'Burstable'

@description('Storage size in GB allocated to PostgreSQL Flexible Server.')
param postgresStorageSizeGB int = 64

@description('Backup retention days for PostgreSQL Flexible Server.')
param postgresBackupRetentionDays int = 7

@description('Allow Azure services to connect to PostgreSQL (firewall rule).')
param postgresAllowAzureServices bool = true

@description('Extra PostgreSQL firewall ranges (objects with startIp/endIp).')
param postgresFirewallRules array = []

var resourceSuffix = '${serviceName}-${environmentName}'
var envTags = {
	'azd-env-name': environmentName
}
var serviceTags = union(envTags, {
	'azd-service-name': azdServiceName
})
var defaultStartupCommand = 'python -m uvicorn main:app --host 0.0.0.0 --port 8000'
var resolvedStartupCommand = empty(startupCommand) ? defaultStartupCommand : startupCommand

var appServicePlanName = '${resourceSuffix}-plan'
var webAppName = '${resourceSuffix}-app'
var redisName = '${resourceSuffix}-redis'
var postgresServerName = '${resourceSuffix}-pg'

module redis './modules/redis.bicep' = {
	name: 'redis'
	params: {
		location: location
		redisName: redisName
		skuName: redisSkuName
		skuFamily: redisSkuFamily
		capacity: redisCapacity
		enableNonSslPort: redisEnableNonSslPort
		minimumTlsVersion: redisMinimumTlsVersion
		tags: envTags
	}
}

module postgres './modules/postgres.bicep' = {
	name: 'postgres'
	params: {
		location: location
		serverName: postgresServerName
		adminUsername: postgresAdminUsername
		adminPassword: postgresAdminPassword
		databaseName: postgresDatabaseName
		version: postgresVersion
		skuName: postgresSkuName
		skuTier: postgresSkuTier
		storageSizeGB: postgresStorageSizeGB
		backupRetentionDays: postgresBackupRetentionDays
		allowAzureServices: postgresAllowAzureServices
		firewallRules: postgresFirewallRules
		tags: envTags
	}
}

var managedAppSettings = {
	DATABASE_URL: postgres.outputs.connectionString
	PGHOST: postgres.outputs.hostName
	PGPORT: '5432'
	PGDATABASE: postgres.outputs.databaseName
	PGUSER: postgres.outputs.adminUser
	PGPASSWORD: postgres.outputs.password
	REDIS_HOST: redis.outputs.hostName
	REDIS_PORT: redis.outputs.port
	REDIS_PASSWORD: redis.outputs.primaryKey
	REDIS_USE_TLS: redis.outputs.useTls
}

module web './modules/webapp.bicep' = {
	name: 'web-app'
	params: {
		location: location
		appServicePlanName: appServicePlanName
		appServiceSkuName: appServiceSkuName
		appServiceSkuTier: appServiceSkuTier
		webAppName: webAppName
		containerImage: containerImage
		containerRegistryServer: containerRegistryServer
		containerRegistryUsername: containerRegistryUsername
		containerRegistryPassword: containerRegistryPassword
		customDomainName: customDomainName
		startupCommand: resolvedStartupCommand
		planTags: envTags
		siteTags: serviceTags
		appSettings: union(managedAppSettings, appSettings)
	}
}

output webAppName string = web.outputs.webAppName
output webAppDefaultHostname string = web.outputs.defaultHostname
output webAppHostname string = web.outputs.hostname
output redisHostName string = redis.outputs.hostName
output redisPort string = redis.outputs.port
output redisPrimaryKey string = redis.outputs.primaryKey
output postgresHostName string = postgres.outputs.hostName
output postgresDatabaseName string = postgres.outputs.databaseName
output postgresConnectionString string = postgres.outputs.connectionString
