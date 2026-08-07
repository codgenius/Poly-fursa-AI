# Archived Task 5 EC2 Deployment Orchestration

> Historical learning document: this describes the retired Task 5
> Docker Compose deployment to dedicated development and production EC2
> instances. Task 6 replaces these workflows with Terraform, Kubernetes,
> Argo CD, and the current `cluster.yaml` and `cd.yaml` workflows.

# Deployment Orchestration

## Overview

The `feature/deployment` work replaces five independently triggered deployment workflows with one orchestrated deployment pipeline.

Previously, each deployment workflow listened for pushes by itself:

```yaml
on:
  push:
    branches:
      - main
      - dev
    paths:
      - 'services/yolo/**'
      - '.github/workflows/deploy-yolo.yml'

concurrency:
  group: polyai-deploy-${{ github.ref_name }}
  cancel-in-progress: false
```

Each service had its own version of this trigger with its own paths. The workflows could all be triggered by the same push, but GitHub Actions did not know the required deployment order.

The new design has one push-triggered orchestrator:

```text
.github/workflows/deploy.yml
```

The five existing deployment workflows are now reusable workflows:

```text
.github/workflows/deploy-infrastructure.yml
.github/workflows/deploy-mcp.yml
.github/workflows/deploy-yolo.yml
.github/workflows/deploy-agent.yml
.github/workflows/deploy-frontend.yml
```

## Problems Solved

### Uncontrolled deployment order

Independent workflows did not express relationships between services. If one push changed infrastructure, MCP, YOLO, and Agent, GitHub could start their workflows without guaranteeing the required order.

The orchestrator now enforces:

```text
Infrastructure -> MCP -> YOLO -> Agent -> Frontend
```

Agent is deployed only after both MCP and YOLO have either deployed successfully or were skipped because they did not change.

### Race conditions on the remote server

Every deployment connects to the same environment and operates on shared state:

- `/home/ubuntu/Poly-fursa-AI`
- The checked-out Git branch
- The root `.env` file
- The same Docker Compose project

Concurrent SSH deployments could interfere with each other. For example, two deployments could run `git checkout`, `git pull`, modify `.env`, or invoke Docker Compose at the same time.

The orchestrator serializes deployment jobs. Only one remote deployment for a branch/environment can progress at a time.

### Duplicate deployment triggers

Previously, push and path logic was repeated across five files. The deployment entry point is now centralized in `deploy.yml`. This prevents separate deployment workflows from independently reacting to the same push.

### Unnecessary deployments

The orchestrator detects which parts of the repository changed. It calls only the reusable workflows for affected areas. It does not deploy every service on every push.

For example, changing `services/agent/README.md` deploys Agent only. Infrastructure, MCP, YOLO, and Frontend are skipped.

## Push Trigger

Only `deploy.yml` listens for deployment pushes:

```yaml
on:
  push:
    branches:
      - main
      - dev
```

This means:

- A push to `dev` can deploy to the development server.
- A push to `main` can deploy to the production server.
- A push to another branch does not start this deployment workflow.
- Pull requests are not deployments. The existing test workflow still handles pull requests to `main`.

## Concurrency

The orchestrator contains:

```yaml
concurrency:
  group: polyai-deploy-${{ github.ref_name }}
  cancel-in-progress: false
```

### `group`

`github.ref_name` is the short name of the branch that received the push, such as `dev` or `main`.

This creates separate concurrency groups:

```text
polyai-deploy-dev
polyai-deploy-main
```

GitHub allows only one workflow run in the same group to be active at a time. A second push to `dev` waits for the active `dev` deployment instead of racing it.

Dev and production have different groups because they use different servers and remote working directories.

### `cancel-in-progress: false`

An active deployment is not cancelled when a newer push arrives. The newer run waits. Interrupting a deployment halfway through could leave the remote `.env` or Docker Compose services in an inconsistent state.

## Detecting Changed Areas

The first job is named `changes`:

```yaml
changes:
  runs-on: ubuntu-latest
```

It checks out the triggering commit:

```yaml
- name: Checkout code
  uses: actions/checkout@v4
```

It then runs the path-filter action:

```yaml
- name: Detect changed deployment areas
  id: filter
  uses: dorny/paths-filter@v3
  with:
    base: ${{ github.ref }}
    filters: |
      # filter definitions
```

### `id: filter`

The step ID gives later expressions a stable name for reading the action's outputs:

```yaml
steps.filter.outputs.agent
```

### `base: ${{ github.ref }}`

`github.ref` is the full Git reference that triggered the workflow:

```text
refs/heads/dev
refs/heads/main
```

Because the comparison base is the same branch that received the push, the action detects changes between the branch state before the push and its state after the push.

This setting fixes an important bug. Without it, `paths-filter` used the repository's default branch as its base. A push to `dev` was compared against `main`, so all existing differences between `main` and `dev` were treated as new changes. That incorrectly caused every service to deploy.

With the explicit base:

```text
Push to dev  -> compare previous dev with new dev
Push to main -> compare previous main with new main
```

For a push containing multiple commits, the combined changed files from that push are evaluated.

### Filters

A filter is a named collection of path patterns. If at least one changed file matches a pattern, the filter output is the string `'true'`. Otherwise, it is `'false'`.

The infrastructure filter is:

```yaml
infrastructure:
  - 'docker-compose.yml'
  - 'fluent-bit.conf'
  - 'monitoring/**'
  - 'infra/**'
  - '.env.example'
  - '.github/workflows/deploy-infrastructure.yml'
```

The service filters are:

```yaml
mcp:
  - 'services/img-proc-mcp/**'
  - '.github/workflows/deploy-mcp.yml'

yolo:
  - 'services/yolo/**'
  - '.github/workflows/deploy-yolo.yml'

agent:
  - 'services/agent/**'
  - '.github/workflows/deploy-agent.yml'

frontend:
  - 'services/frontend/**'
  - '.github/workflows/deploy-frontend.yml'
```

`**` means any file or nested directory below that path. Therefore, all of these match the Agent filter:

```text
services/agent/app.py
services/agent/README.md
services/agent/tests/test_api.py
```

Including each reusable workflow file in its filter means changing a service's deployment instructions also deploys that service.

### Job outputs

The `changes` job exposes the step results to other jobs:

```yaml
outputs:
  infrastructure: ${{ steps.filter.outputs.infrastructure }}
  mcp: ${{ steps.filter.outputs.mcp }}
  yolo: ${{ steps.filter.outputs.yolo }}
  agent: ${{ steps.filter.outputs.agent }}
  frontend: ${{ steps.filter.outputs.frontend }}
```

Other jobs read them through the `needs` context:

```yaml
needs.changes.outputs.agent
```

## Reusable Workflows

The five original deployment workflows changed from `push` to:

```yaml
on:
  workflow_call:
```

`workflow_call` means the file contains a reusable workflow. It does not start independently when code is pushed. Another workflow must call it.

The orchestrator calls a reusable workflow at the job level:

```yaml
deploy-agent:
  uses: ./.github/workflows/deploy-agent.yml
  secrets: inherit
```

The relative `uses` path points to a workflow in the same repository and at the same commit as the calling workflow.

### Secrets

```yaml
secrets: inherit
```

This passes the caller's available repository secrets into the reusable workflow. The existing workflows can continue using:

```text
DOCKERHUB_USERNAME
DOCKERHUB_TOKEN
DEV_INSTANCE_SSH_KEY
PROD_INSTANCE_SSH_KEY
```

Secret values are not copied into the YAML and are not printed by this configuration.

### Branch and commit context

The reusable workflows keep the caller's event context. Their existing expressions still work:

```yaml
if: github.ref == 'refs/heads/dev'
if: github.ref == 'refs/heads/main'
```

They also retain `github.sha`, so image tags continue to identify the commit that triggered the orchestrator.

## Dependency Order with `needs`

`needs` tells GitHub that one job depends on other jobs.

For example, Agent declares:

```yaml
needs:
  - changes
  - deploy-infrastructure
  - deploy-mcp
  - deploy-yolo
```

GitHub does not evaluate Agent until these earlier jobs have reached a final result.

The complete ordering is:

```text
changes
  -> deploy-infrastructure
    -> deploy-mcp
      -> deploy-yolo
        -> deploy-agent
          -> deploy-frontend
```

Later jobs list all relevant earlier jobs, not only the immediately previous job. This ensures that a real failure cannot be hidden behind an intermediate skipped job.

## Job Conditions

The Agent condition is:

```yaml
if: |
  always() &&
  needs.changes.result == 'success' &&
  needs.changes.outputs.agent == 'true' &&
  (needs.deploy-infrastructure.result == 'success' || needs.deploy-infrastructure.result == 'skipped') &&
  (needs.deploy-mcp.result == 'success' || needs.deploy-mcp.result == 'skipped') &&
  (needs.deploy-yolo.result == 'success' || needs.deploy-yolo.result == 'skipped')
```

### `always()`

By default, a job with `needs` may be skipped if a required job was skipped. That would cause an Agent change to be skipped whenever unchanged MCP or YOLO jobs were skipped.

`always()` tells GitHub to evaluate the complete condition regardless of whether a needed job succeeded, failed, or was skipped. It does not mean the deployment always runs. The remaining conditions still decide whether it is safe and necessary.

### Successful change detection

```yaml
needs.changes.result == 'success'
```

Deployments do not run if checkout or path detection failed. Deploying without reliable change information could deploy the wrong components.

### Service changed

```yaml
needs.changes.outputs.agent == 'true'
```

Agent runs only when an Agent path matched.

### Accepting skipped prerequisites

```yaml
needs.deploy-mcp.result == 'success' ||
needs.deploy-mcp.result == 'skipped'
```

Both results are safe:

- `success`: MCP changed and deployed successfully.
- `skipped`: MCP did not change, so no MCP deployment was needed.

### Blocking failures

`failure` and `cancelled` are not accepted by the condition. If MCP or YOLO deployment fails, Agent does not run. Frontend also checks every earlier deployment, so a failure anywhere stops the remaining sequence.

## Preserved Service Deployment Logic

The orchestration changes how workflows are started and ordered. It does not replace their service-specific deployment steps.

The existing behavior remains:

1. Check out the triggering commit on the GitHub runner.
2. Configure Docker Buildx.
3. Log in to DockerHub.
4. Generate an image tag:

   ```text
   YYYYMMDD-HHMMSS-github-sha
   ```

5. Build and push the affected service image.
6. Connect to the correct server with SSH.
7. Check out and pull `dev` or `main` on that server.
8. Update the service's image tag in the root `.env`.
9. Pull and restart only that service.

The service-specific Compose commands remain:

```text
docker compose pull <service>
docker compose up -d --no-deps <service>
docker compose ps <service>
```

`--no-deps` tells Docker Compose not to restart dependent services automatically. The orchestrator already controls which changed services are deployed and in what order.

Infrastructure remains different from a service deployment. It preserves the existing full-stack Compose behavior:

```text
docker compose pull
docker compose up -d
docker compose ps
```

No Kubernetes deployment or `kubectl apply` behavior was added.

## Example Scenarios

### Root README change

```text
Changed: README.md
Result: changes job runs; every deployment job is skipped
```

### Agent README change

```text
Changed: services/agent/README.md
Result: Agent deploys; Infrastructure, MCP, YOLO, and Frontend are skipped
```

Agent is allowed to run because skipped unchanged prerequisites are accepted.

### MCP and Agent change

```text
Changed: services/img-proc-mcp/app.py
Changed: services/agent/app.py
Result: MCP deploys first, then Agent
```

### YOLO and Agent change

```text
Changed: services/yolo/app.py
Changed: services/agent/app.py
Result: YOLO deploys first, then Agent
```

### Infrastructure and Frontend change

```text
Changed: docker-compose.yml
Changed: services/frontend/app/page.tsx
Result: Infrastructure deploys first, then Frontend
```

The unchanged MCP, YOLO, and Agent jobs are skipped without preventing Frontend from running.

### Failed YOLO deployment

```text
YOLO result: failure
Agent result: skipped
Frontend result: skipped
```

This prevents dependent services from deploying after a failed prerequisite deployment.

## How to Verify a Run

In GitHub:

1. Open the repository's **Actions** tab.
2. Select **Deploy Changed Services**.
3. Open the relevant workflow run.
4. Select the **changes** job.
5. Expand **Detect changed deployment areas**.

The log reports the comparison and filter results:

```text
Filter infrastructure = false
Filter mcp = false
Filter yolo = false
Filter agent = true
Filter frontend = false
```

The workflow graph should show only the matching service deployments in green. Unchanged deployment jobs should show the skipped symbol.

## Files Changed by This Feature

```text
.github/workflows/deploy.yml                 New push-triggered orchestrator
.github/workflows/deploy-infrastructure.yml  Converted to workflow_call
.github/workflows/deploy-mcp.yml             Converted to workflow_call
.github/workflows/deploy-yolo.yml            Converted to workflow_call
.github/workflows/deploy-agent.yml           Converted to workflow_call
.github/workflows/deploy-frontend.yml        Converted to workflow_call
```

`.github/workflows/test.yaml` was not changed by the deployment orchestration work.
