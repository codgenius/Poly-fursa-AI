import gzip
import io
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError
from fastmcp import FastMCP


mcp = FastMCP("observability")

SERVICE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
MAX_QUERY_HOURS = 24
MAX_RESULTS = 500
MAX_OBJECTS = 500
MAX_COMPRESSED_BYTES = 25 * 1024 * 1024
MAX_DECOMPRESSED_BYTES_PER_OBJECT = 10 * 1024 * 1024


def _environment_config(environment: str) -> tuple[str, str]:
    """Return the configured S3 bucket and log host for dev or prod."""
    environment = environment.lower().strip()
    if environment not in {"dev", "prod"}:
        raise ValueError("environment must be 'dev' or 'prod'")

    prefix = environment.upper()
    bucket = os.environ.get(f"{prefix}_S3_LOGS_BUCKET", "").strip()
    host = os.environ.get(f"{prefix}_LOG_HOST", f"polyai-{environment}").strip()

    if not bucket or bucket.startswith("REPLACE_WITH_"):
        raise ValueError(f"{prefix}_S3_LOGS_BUCKET is not configured")

    return bucket, host


def _parse_timestamp(value: str, field_name: str) -> datetime:
    """Parse an ISO-8601 timestamp and normalize it to UTC."""
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            f"{field_name} must be an ISO-8601 timestamp, for example "
            "2026-07-14T20:00:00Z"
        ) from exc

    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone, such as Z or +03:00")

    return parsed.astimezone(timezone.utc)


def _time_range(start_time: str, end_time: str) -> tuple[datetime, datetime]:
    """Resolve an explicit range or default to the most recent five minutes."""
    if not start_time and not end_time:
        end = datetime.now(timezone.utc)
        return end - timedelta(minutes=5), end

    if not start_time or not end_time:
        raise ValueError("start_time and end_time must be provided together")

    start = _parse_timestamp(start_time, "start_time")
    end = _parse_timestamp(end_time, "end_time")

    if start >= end:
        raise ValueError("start_time must be earlier than end_time")
    if end - start > timedelta(hours=MAX_QUERY_HOURS):
        raise ValueError(f"log queries are limited to {MAX_QUERY_HOURS} hours")

    return start, end


def _hour_prefixes(base_prefix: str, start: datetime, end: datetime) -> list[str]:
    """Build hour prefixes, including the preceding hour for upload-boundary overlap."""
    current = start.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    final = end.replace(minute=0, second=0, microsecond=0)
    prefixes = []

    while current <= final:
        prefixes.append(f"{base_prefix}{current:%Y/%m/%d/%H}/")
        current += timedelta(hours=1)

    return prefixes


def _list_objects(client: Any, bucket: str, prefixes: list[str]) -> list[dict[str, Any]]:
    """List candidate objects under a bounded set of S3 prefixes."""
    objects: dict[str, dict[str, Any]] = {}
    paginator = client.get_paginator("list_objects_v2")

    for prefix in prefixes:
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                key = item["Key"]
                if not key.endswith(".gz"):
                    continue
                objects[key] = item
                if len(objects) > MAX_OBJECTS:
                    raise ValueError(
                        f"query matched more than {MAX_OBJECTS} S3 objects; "
                        "use a shorter time range"
                    )

    total_size = sum(int(item.get("Size", 0)) for item in objects.values())
    if total_size > MAX_COMPRESSED_BYTES:
        raise ValueError(
            "query matched too much compressed log data; use a shorter time range"
        )

    return sorted(objects.values(), key=lambda item: item["Key"])


def _read_records(client: Any, bucket: str, key: str) -> list[dict[str, Any]]:
    """Download one gzip object and parse its newline-delimited JSON records."""
    response = client.get_object(Bucket=bucket, Key=key)
    body = response["Body"]

    try:
        with gzip.GzipFile(fileobj=body, mode="rb") as compressed:
            payload = compressed.read(MAX_DECOMPRESSED_BYTES_PER_OBJECT + 1)
    finally:
        body.close()

    if len(payload) > MAX_DECOMPRESSED_BYTES_PER_OBJECT:
        raise ValueError(f"decompressed S3 object is too large: {key}")

    records = []
    for line in io.BytesIO(payload):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(record, dict):
            records.append(record)

    return records


def _record_timestamp(record: dict[str, Any]) -> datetime | None:
    value = record.get("time") or record.get("date")
    if not isinstance(value, str):
        return None
    try:
        return _parse_timestamp(value, "record time")
    except ValueError:
        return None


def _aws_error(exc: ClientError) -> ValueError:
    code = exc.response.get("Error", {}).get("Code", "Unknown")
    if code in {"AccessDenied", "403"}:
        return ValueError("AWS denied access to the configured logs bucket")
    if code in {"NoSuchBucket", "404"}:
        return ValueError("the configured logs bucket does not exist")
    return ValueError(f"S3 request failed with AWS error code: {code}")


@mcp.tool()
def list_log_services(environment: str = "dev") -> dict[str, Any]:
    """List service names that have Fluent Bit log prefixes in an environment."""
    bucket, host = _environment_config(environment)
    base_prefix = f"logs/host={host}/"
    client = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))

    services = set()
    paginator = client.get_paginator("list_objects_v2")
    try:
        for page in paginator.paginate(Bucket=bucket, Prefix=base_prefix, Delimiter="/"):
            for item in page.get("CommonPrefixes", []):
                child = item["Prefix"][len(base_prefix):].rstrip("/")
                if child.startswith("service="):
                    services.add(child.removeprefix("service="))
    except ClientError as exc:
        raise _aws_error(exc) from exc

    return {
        "environment": environment.lower(),
        "host": host,
        "services": sorted(services),
    }


@mcp.tool()
def get_logs(
    service: str,
    environment: str = "dev",
    start_time: str = "",
    end_time: str = "",
    query: str = "",
    level: str = "",
    limit: int = 100,
) -> dict[str, Any]:
    """Retrieve logs for one service and exact time range from service-partitioned S3 objects.

    If start_time and end_time are omitted, the most recent five minutes are used.
    Timestamps must be ISO-8601 and include a timezone. The optional query and level
    filters are case-insensitive substring matches against the log message.
    """
    service = service.strip()
    if not SERVICE_NAME_PATTERN.fullmatch(service):
        raise ValueError("service contains unsupported characters")
    if limit < 1 or limit > MAX_RESULTS:
        raise ValueError(f"limit must be between 1 and {MAX_RESULTS}")

    bucket, host = _environment_config(environment)
    start, end = _time_range(start_time, end_time)
    base_prefix = f"logs/host={host}/service={service}/"
    prefixes = _hour_prefixes(base_prefix, start, end)
    client = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))

    try:
        objects = _list_objects(client, bucket, prefixes)
        matches = []
        query_lower = query.lower().strip()
        level_lower = level.lower().strip()

        for item in objects:
            for record in _read_records(client, bucket, item["Key"]):
                timestamp = _record_timestamp(record)
                if timestamp is None or timestamp < start or timestamp > end:
                    continue

                message = str(record.get("log", ""))
                message_lower = message.lower()
                if query_lower and query_lower not in message_lower:
                    continue
                if level_lower and level_lower not in message_lower:
                    continue

                matches.append(
                    {
                        "time": timestamp.isoformat().replace("+00:00", "Z"),
                        "service": service,
                        "host": record.get("host", host),
                        "stream": record.get("stream"),
                        "log": message,
                    }
                )

        matches.sort(key=lambda record: record["time"])
        truncated = len(matches) > limit
        matches = matches[-limit:]
    except ClientError as exc:
        raise _aws_error(exc) from exc

    return {
        "environment": environment.lower(),
        "service": service,
        "start_time": start.isoformat().replace("+00:00", "Z"),
        "end_time": end.isoformat().replace("+00:00", "Z"),
        "objects_scanned": len(objects),
        "result_count": len(matches),
        "truncated": truncated,
        "logs": matches,
    }


def _prometheus_url(environment: str) -> str:
    environment = environment.strip().lower()
    if environment not in {"dev", "prod"}:
        raise ValueError("environment must be 'dev' or 'prod'")
    variable = f"{environment.upper()}_PROMETHEUS_URL"
    url = os.environ.get(variable, "").strip().rstrip("/")
    if not url:
        raise ValueError(f"{variable} is not configured")
    return url


def _parse_metric_time(value: str, default: datetime) -> datetime:
    if not value:
        return default
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _prometheus_request(url: str, parameters: dict[str, str]) -> dict:
    import json
    from urllib.error import HTTPError, URLError
    from urllib.parse import urlencode
    from urllib.request import urlopen

    try:
        with urlopen(f"{url}?{urlencode(parameters)}", timeout=15) as response:
            payload = json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"Prometheus returned HTTP {error.code}") from error
    except URLError as error:
        raise RuntimeError(f"Could not connect to Prometheus: {error.reason}") from error
    if payload.get("status") != "success":
        raise RuntimeError(payload.get("error", "Prometheus query failed"))
    return payload.get("data", {})


@mcp.tool()
def query_prometheus(
    query: str,
    environment: str = "dev",
    start_time: str = "",
    end_time: str = "",
    step_seconds: int = 15,
) -> dict:
    """Run a PromQL range query against dev or prod Prometheus.

    Times are ISO-8601. Empty times mean the last five minutes. Queries are
    limited to 24 hours.
    """
    if not query.strip():
        raise ValueError("query must not be empty")
    if step_seconds < 1 or step_seconds > 3600:
        raise ValueError("step_seconds must be between 1 and 3600")

    now = datetime.now(timezone.utc)
    end = _parse_metric_time(end_time, now)
    start = _parse_metric_time(start_time, end - timedelta(minutes=5))
    if start >= end:
        raise ValueError("start_time must be earlier than end_time")
    if end - start > timedelta(hours=24):
        raise ValueError("metric queries are limited to 24 hours")

    data = _prometheus_request(
        f"{_prometheus_url(environment)}/api/v1/query_range",
        {
            "query": query.strip(),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "step": str(step_seconds),
        },
    )
    return {
        "environment": environment.lower(),
        "query": query.strip(),
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
        "result_type": data.get("resultType"),
        "series": data.get("result", []),
    }


@mcp.tool()
def get_cpu_usage(
    environment: str = "dev",
    start_time: str = "",
    end_time: str = "",
    step_seconds: int = 15,
) -> dict:
    """Get EC2 CPU usage percentage from node-exporter for a time range."""
    return query_prometheus(
        query=(
            "100 - (avg by (instance) "
            "(rate(node_cpu_seconds_total{mode=\"idle\"}[5m])) * 100)"
        ),
        environment=environment,
        start_time=start_time,
        end_time=end_time,
        step_seconds=step_seconds,
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
