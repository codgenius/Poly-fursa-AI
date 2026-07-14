# Observability MCP Server

Local stdio MCP server for querying service-partitioned container logs in S3.

## Tools

- `list_log_services(environment)`: lists services with log prefixes.
- `get_logs(service, environment, start_time, end_time, query, level, limit)`: retrieves a bounded time range of logs for one service.

When `start_time` and `end_time` are omitted, `get_logs` searches the most recent five minutes. Explicit timestamps must include a timezone, for example `2026-07-14T20:00:00Z`.

## Required environment

```text
AWS_REGION
DEV_S3_LOGS_BUCKET
PROD_S3_LOGS_BUCKET
DEV_LOG_HOST
PROD_LOG_HOST
```

AWS credentials are resolved using the normal boto3 credential chain. The identity needs read-only access to list the configured bucket prefixes and retrieve log objects.

Install the dependencies yourself from the repository root:

```bash
pip install -r services/observability-mcp/requirements.txt
```

VS Code starts the server through `.vscode/mcp.json` using stdio transport.
