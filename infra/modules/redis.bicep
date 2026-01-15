@description('Azure region for the Redis cache.')
param location string

@description('Redis resource name (must be globally unique).')
param redisName string

@description('Redis SKU name (Basic, Standard, Premium).')
param skuName string = 'Basic'

@description('Redis SKU family (C for Basic/Standard, P for Premium).')
param skuFamily string = 'C'

@description('Redis capacity (0 = 250MB, 1 = 1GB, etc.).')
param capacity int = 0

@description('Whether to enable the non-SSL port 6379. Defaults to false to require TLS.')
param enableNonSslPort bool = false

@description('Minimum TLS version enforced on the cache.')
param minimumTlsVersion string = '1.2'

@description('Additional Redis configuration key/value pairs.')
param redisConfiguration object = {
  'maxmemory-reserved': '10'
}

@description('Tags applied to the Redis cache.')
param tags object = {}

var redisApiVersion = '2023-08-01'
var redisPort = enableNonSslPort ? '6379' : '6380'
var redisUseTls = enableNonSslPort ? 'false' : 'true'

resource redisCache 'Microsoft.Cache/Redis@2023-08-01' = {
  name: redisName
  location: location
  tags: tags
  properties: {
    sku: {
      name: skuName
      family: skuFamily
      capacity: capacity
    }
    enableNonSslPort: enableNonSslPort
    minimumTlsVersion: minimumTlsVersion
    redisConfiguration: redisConfiguration
  }
}

var redisKeys = listKeys(redisCache.id, redisApiVersion)

output name string = redisCache.name
output hostName string = redisCache.properties.hostName
output port string = redisPort
output primaryKey string = redisKeys.primaryKey
output useTls string = redisUseTls
