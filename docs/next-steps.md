# Next Steps after `azd init`

> Need the bigger picture? See the [documentation hub](README.md) for the complete map of project guides.

## Table of Contents

1. [Next Steps](#next-steps)
   1. [Provision infrastructure](#provision-infrastructure-and-deploy-application-code)
   2. [Modify infrastructure](#modify-infrastructure)
   3. [Getting to production-ready](#getting-to-production-ready)
2. [Billing](#billing)
3. [Troubleshooting](#troubleshooting)

## Next Steps

### Provision infrastructure and deploy application code

Run `azd up` to provision your infrastructure and deploy to Azure in one step (or run `azd provision` then `azd deploy` to accomplish the tasks separately). Visit the service endpoints listed to see your application up-and-running!

To troubleshoot any issues, see [troubleshooting](#troubleshooting).

### Modify infrastructure

To describe the infrastructure and application, `azure.yaml` was added. This file contains all services and resources that describe your application.

To add new services or resources, run `azd add`. You may also edit the `azure.yaml` file directly if needed.

### Getting to production-ready

When needed, `azd` generates the required infrastructure as code in memory and uses it. If you would like to see or modify the infrastructure that `azd` uses, run `azd infra gen` to persist it to disk.

If you do this, some additional directories will be created:

```yaml
- infra/                 # Infrastructure as Code (Bicep) files
  - main.bicep           # orchestrates hosting + data modules
  - modules/
      - webapp.bicep     # App Service plan + Web App (container or code)
      - postgres.bicep   # Azure Database for PostgreSQL Flexible Server
      - redis.bicep      # Azure Cache for Redis
```

*Note*: Once you have generated your infrastructure to disk, those files are the source of truth for azd. Any changes made to `azure.yaml` (such as through `azd add`) will not be reflected in the infrastructure until you regenerate it with `azd infra gen` again. It will prompt you before overwriting files. You can pass `--force` to force `azd infra gen` to overwrite the files without prompting.

Finally, run `azd pipeline config` to configure a CI/CD deployment pipeline.

## Billing

Visit the *Cost Management + Billing* page in Azure Portal to track current spend. For more information about how you're billed, and how you can monitor the costs incurred in your Azure subscriptions, visit [billing overview](https://learn.microsoft.com/azure/developer/intro/azure-developer-billing).

## Troubleshooting

Q: I visited the service endpoint listed, and I'm seeing a blank page, a generic welcome page, or an error page.

A: Your service may have failed to start, or it may be missing some configuration settings. To investigate further:

1. Run `azd show`. Click on the link under "View in Azure Portal" to open the resource group.
2. Navigate to the App Service **Web App** resource associated with the deployment.
3. Use **Diagnose and solve problems** or **Log stream** to inspect application/startup logs.
4. Verify configuration under **Settings → Environment variables** to ensure required secrets were injected.
5. Review the Redis and PostgreSQL resources for availability/connection issues if the app logs indicate database errors.

For more troubleshooting information, visit [App Service diagnostics](https://learn.microsoft.com/azure/app-service/overview-diagnostics). 

### Additional information

For additional information about setting up your `azd` project, visit our official [docs](https://learn.microsoft.com/azure/developer/azure-developer-cli/make-azd-compatible?pivots=azd-convert).
