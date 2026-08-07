# PolyAI

## Setup

Create and activate a virtual environment from the repo root directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Your terminal prompt should now show `(.venv)`. Keep this environment active whenever you run any service.

See each service's README for how to configure and run it.

## Kubernetes deployment

PolyAI can run on a Kubernetes cluster on AWS. Development and production
workloads share one cluster and are separated into the `dev` and `prod`
namespaces.

The `cluster.yaml` GitHub Actions workflow provisions and bootstraps the
cluster for a selected AWS region. Argo CD automatically synchronizes
development changes, while production changes require manual synchronization.