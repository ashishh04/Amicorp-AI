<#
.SYNOPSIS
  Start n8n for local development with the values the workflows read through $env.

.DESCRIPTION
  Community Edition has no Variables feature, so the local workflow copies read $env.X instead of
  $vars.X. Production runs n8n Enterprise with Variables, using the original workflow files.
#>
$env:PLATFORM_API_URL = "http://127.0.0.1:8000"   # the backend: cd backend; python -m app
$env:N8N_WEBHOOK_BASE = "http://127.0.0.1:5678"   # where callbacks reach this n8n
$env:OPS_ALERT_WEBHOOK_URL = ""                    # Teams fallback alert; empty locally
$env:UC4_MAX_NEW_CARDS_PER_RUN = "200"
$env:UC5_MAX_NEW_CARDS_PER_RUN = "200"
$env:REDRIVE_AFTER_MINUTES = "30"
$env:REDRIVE_MAX_ATTEMPTS = "3"

# Let workflow expressions read the variables above.
$env:N8N_BLOCK_ENV_ACCESS_IN_NODE = "false"

n8n start
