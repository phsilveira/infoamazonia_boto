@description('Azure region for the PostgreSQL Flexible Server.')
param location string

@description('Server name (must be globally unique).')
param serverName string

@description('Administrator username for the server.')
param adminUsername string

@secure()
@description('Administrator password for the server.')
param adminPassword string

@description('Default database to create.')
param databaseName string = 'app'

@description('Major PostgreSQL version (e.g., 16).')
param version string = '16'

@description('SKU name (e.g., Standard_B1ms).')
param skuName string = 'Standard_B1ms'

@description('SKU tier (e.g., Burstable, GeneralPurpose).')
param skuTier string = 'Burstable'

@description('Storage size in GB.')
param storageSizeGB int = 64

@description('Backup retention days.')
param backupRetentionDays int = 7

@description('Enable public network access (true by default).')
param publicNetworkAccess bool = true

@description('Allow Azure services through a firewall rule.')
param allowAzureServices bool = true

@description('Custom firewall ranges to allow (array of objects with startIp and endIp).')
param firewallRules array = []

@description('Tags applied to the PostgreSQL resources.')
param tags object = {}

resource server 'Microsoft.DBforPostgreSQL/flexibleServers@2022-12-01' = {
  name: serverName
  location: location
  tags: tags
  sku: {
    name: skuName
    tier: skuTier
  }
  properties: {
    administratorLogin: adminUsername
    administratorLoginPassword: adminPassword
    version: version
    backup: {
      backupRetentionDays: backupRetentionDays
    }
    storage: {
      storageSizeGB: storageSizeGB
      autoGrow: 'Enabled'
    }
    network: {
      publicNetworkAccess: publicNetworkAccess ? 'Enabled' : 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
  }
}

resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2022-12-01' = {
  name: '${server.name}/${databaseName}'
}

resource firewallAllowAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2022-12-01' = if (allowAzureServices && publicNetworkAccess) {
  name: '${server.name}/allow-azure-services'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

resource firewallCustom 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2022-12-01' = [for (rule, idx) in firewallRules: if (publicNetworkAccess) {
  name: '${server.name}/custom-${idx}'
  properties: {
    startIpAddress: rule.startIp
    endIpAddress: rule.endIp
  }
}]

var hostName = format('{0}.postgres.database.azure.com', server.name)
var adminUserWithServer = format('{0}@{1}', adminUsername, serverName)
var connectionString = format('postgresql+psycopg://{0}:{1}@{2}:5432/{3}?sslmode=require', adminUserWithServer, uriComponent(adminPassword), hostName, databaseName)

output hostName string = hostName
output adminUser string = adminUserWithServer
output password string = adminPassword
output databaseName string = databaseName
output connectionString string = connectionString
output serverId string = server.id
