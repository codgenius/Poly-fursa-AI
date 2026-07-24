# Task 6 Implementation Plan and Progress Tracker

## Purpose

This file is the shared plan and progress tracker for Task 6.

Task 6 provisions one self-managed Kubernetes cluster on AWS with Terraform,
then installs Calico and ArgoCD and deploys the existing PolyAI Kubernetes
workloads through GitOps.

The implementation will be completed in small, explicitly approved phases.
No undecided architecture choice should be implemented before it is explained
and approved.

## Sources of Truth

Use these sources in this order:

1. `task6.md` — authoritative Task 6 assignment.
2. Course tutorial files supplied by the student, currently:
   - `/home/hadikhier/Fursa26-task6-reference/tutorials/k8s_cluster_setup.md`
   - `/home/hadikhier/Fursa26-task6-reference/tutorials/k8s_core_objects.md`
   - `/home/hadikhier/Fursa26-task6-reference/tutorials/k8s_data_persistence.md`
   - `/home/hadikhier/Fursa26-task6-reference/tutorials/k8s_argocd.md`
   - `/home/hadikhier/Fursa26-task6-reference/tutorials/k8s_pod_design.md`
   - `/home/hadikhier/Fursa26-task6-reference/tutorials/tf_basics.md`
   - `/home/hadikhier/Fursa26-task6-reference/tutorials/tf_variables.md`
   - `/home/hadikhier/Fursa26-task6-reference/tutorials/tf_modules.md`
3. `task5` — authoritative Task 5 assignment and scope.
4. Existing working Task 5 repository files and manifests.
5. `TASK6_CODEX_HANDOF.md` — planning context only; it was AI-assisted and is
   not authoritative when it differs from the assignment.

## Working Rules

- Provision exactly one cluster containing both `dev` and `prod` namespaces.
- Preserve the old manually created EC2/Docker Compose deployment.
- Do not import, change, stop, or destroy the old infrastructure.
- Do not provision AWS resources or run Terraform, kubectl, or SSH without
  explicit approval for that phase.
- Do not make implementation decisions silently.
- Explain each undecided choice in student-friendly terms before requesting
  approval.
- Use only assignment-required or course-taught technology unless something
  additional is technically necessary and approved.
- Keep the implementation explicit and readable.
- The final destroy/recreate test requires separate destructive-action approval.

## Important Network Clarification

The assignment requires two public subnets in different **Availability Zones**,
not different AWS regions.

For the first implementation:

- AWS region: `us-east-1` (N. Virginia).
- VPC: one VPC in `us-east-1`.
- Public subnets: two subnets in two different AZs within `us-east-1`.
- Exact AZ names are regional configuration values in the matching `.tfvars`
  file, not constants inside the reusable module.
- Each regional `.tfvars` file must provide exactly two different AZs that
  belong to its selected region.

Portability to another region is achieved by:

1. selecting a regional Terraform workspace;
2. supplying the matching regional `.tfvars` file;
3. discovering the AMI in that region and supplying two matching AZ names in
   the regional `.tfvars` file.

The assignment explicitly says a second region does not need to be provisioned.

## Confirmed Assignment Requirements

### Infrastructure

- All Terraform files live under `infra/tf/`.
- Use the AWS VPC module taught in class.
- Create two public subnets in different AZs.
- Put all cluster instances in those public subnets.
- Create a local `modules/k8s-cluster` Terraform module.
- Create one Ubuntu `t3.medium` control-plane EC2 instance.
- Give the control plane a 20 GiB root volume.
- Attach:
  - `AmazonEKSClusterPolicy`
  - `AmazonEBSCSIDriverPolicy`
  - `AmazonEC2ContainerRegistryReadOnly`
- Allow SSH and all intra-VPC traffic.
- Automatically install CRI-O, kubelet, kubeadm, and kubectl.
- Automatically run `kubeadm init`.
- Manage workers with a Launch Template and Auto Scaling Group.
- Worker ASG values:
  - `min_size = 1`
  - `max_size = 3`
  - `desired_capacity > 0` while working
  - `desired_capacity = 0` when finished to reduce worker cost
- New workers must automatically join with a valid `kubeadm join` command.
- The same Terraform configuration must work in other regions through a
  workspace and regional `.tfvars` file.
- Only one region must actually be provisioned.

### Manual bootstrap before automation

- Install Calico manually.
- Install ArgoCD manually.
- Retrieve the ArgoCD initial admin password.
- Create an ArgoCD Application per microservice.
- Development watches `dev` and synchronizes automatically.
- Production watches `main` and synchronizes manually.

### Automation

- Create `.github/workflows/cluster.yaml`.
- Trigger `cluster.yaml` manually with a region input.
- Give it sequential Provision and Bootstrap jobs.
- Provision runs Terraform for the selected region.
- Bootstrap obtains the control-plane IP from Terraform output.
- Bootstrap connects to the control plane through SSH.
- Bootstrap idempotently installs Calico, ArgoCD, and the Applications.
- Create `.github/workflows/cd.yaml`.
- Trigger `cd.yaml` on pushes to `dev` and `main`.
- Build/update only changed services.
- Update the corresponding Kubernetes image tag.
- Commit that manifest update so ArgoCD detects it.
- Preserve production manual synchronization.

### Task 5 requirements that remain relevant

- Continue using plain Kubernetes objects; do not replace them with Helm charts
  or operators.
- Deploy the Docker Compose application services to both namespaces.
- Prometheus requires durable EBS-backed storage.
- Use the EBS CSI driver for Prometheus persistence.
- Keep the old Docker Compose deployment running.

## Current Repository Baseline

- Current implementation branch:
  `feature/kubernetes-cluster-provisioning-as-code`.
- Baseline commit: `9ae78e4`.
- The feature branch is currently identical to local `main`.
- The feature branch was created from the merged Task 5 work on `main`.
- No Terraform configuration exists.
- No ArgoCD manifests exist.
- No `cluster.yaml` or `cd.yaml` exists.
- Existing Kubernetes namespaces: `dev` and `prod`.
- Existing Kubernetes workloads:
  - Image Processing MCP
  - YOLO
  - Agent
  - Frontend
  - Prometheus
  - Grafana
- Node Exporter exists in Docker Compose and Task 5 planning, but its Kubernetes
  manifests are absent.
- Observability MCP is a local Task 5 developer tool and is not currently a
  Kubernetes workload.
- Current registry: Docker Hub.
- Existing application repositories:
  - `hadikhier/img-proc-mcp`
  - `hadikhier/yolo-service`
  - `hadikhier/agent-service`
  - `hadikhier/frontend-service`
- Current Kubernetes Services are all `ClusterIP`.
- Existing Task 5 deployment workflows deploy Docker Compose to old EC2 hosts.
- Those workflows must remain until the new cluster is proven.
- The old development/production systemd unit files that exist on local `dev`
  are not present on `main` or the Task 6 feature branch.
- YOLO uses Kubernetes' default rolling Deployment strategy on `main` and the
  Task 6 feature branch. The older local `dev` branch still declares
  `strategy.type: Recreate`; that older behavior must not be copied into Task 6.

### Branch comparison refreshed on 2026-07-23

`feature/kubernetes-cluster-provisioning-as-code` versus `main`:

- No committed differences.

Local `dev` versus the Task 6 feature branch:

- `dev` adds `strategy.type: Recreate` to both YOLO Deployments.
- `dev` contains six old systemd unit files that are absent from the feature
  branch.
- `dev` contains a duplicate `typing` import in `services/yolo/app.py`.

None of these differences requires a Task 6 architecture change. The feature
branch and `main` are the authoritative implementation baseline. Do not copy
the three differences above into Task 6 merely to make `dev` identical.

## Known Manifest Compatibility Problems

These are findings, not approved fixes:

- The frontend browser cannot resolve `http://agent:8000`.
- `NEXT_PUBLIC_AGENT_URL` is baked into the frontend at image build time; a pod
  runtime environment variable alone does not change the browser bundle.
- Agent and YOLO require S3 access; Agent also requires Bedrock access.
- No safe Kubernetes AWS credential mechanism is configured.
- EKS IRSA does not apply to this self-managed kubeadm cluster.
- YOLO defines PVC files but its Deployments use `emptyDir`.
- Prometheus PVs contain hardcoded Task 5 EBS volume IDs.
- Prometheus is pinned to `us-east-1b`.
- `ebs-sc` is referenced but no StorageClass manifest exists.
- The EBS CSI driver is not installed by the repository.
- Grafana's administrator password is hardcoded as `admin`.
- Node Exporter Kubernetes resources are missing.
- Prometheus does not currently scrape Node Exporter.
- Existing workload image tags are hardcoded.
- Existing Task 5 deployment workflows would conflict with the final GitOps
  workflow if both remained active permanently.

The unused YOLO PVC manifests are not a Task 6 persistence requirement. The
student confirmed that durable YOLO storage was intentionally deferred during
Task 5 with the instructor's approval. Task 6 must not expand EBS persistence
to YOLO unless the instructor or a later requirement asks for it.

Prometheus remains different: Task 5 explicitly requires Prometheus to use
durable EBS-backed storage through the EBS CSI driver.

## Course-Confirmed Terraform Module Design

The following points are confirmed by `tf_modules.md`:

- Use `terraform-aws-modules/vpc/aws` version `5.8.1`.
- The root module passes input values into reusable child modules.
- Child-module outputs connect resources and expose values to the root module.
- The VPC ID and public subnet IDs should come from VPC module outputs.
- The AWS provider region should come from a Terraform variable.
- The tutorial demonstrates `aws_availability_zones`; the approved Task 6
  implementation instead makes the two AZ names explicit regional `.tfvars`
  values while keeping them out of the reusable module.
- Use `aws_ami` with Canonical owner ID `099720109477` instead of hardcoding a
  regional AMI ID.
- A separate `providers.tf` is consistent with the course's module example.

The tutorial example passes discovered AZ names to the VPC module. The approved
Task 6 implementation passes exactly two AZ names and two subnet CIDRs from the
selected regional `.tfvars` file. A second region uses a second regional file;
the module code remains unchanged.

The tutorial's Ubuntu 20.04 AMI filter is an example from the course, but the
final Ubuntu release remains undecided until it is checked against the
Kubernetes and CRI-O versions used by the course.

## Course-Confirmed Kubernetes and GitOps Design

The following points are confirmed by tutorials 35–39:

- The cluster is a self-managed kubeadm cluster, not EKS.
- Use Ubuntu EC2 instances and CRI-O; do not install Docker as the Kubernetes
  container runtime.
- The course bootstrap currently sets `kubernetes_version=v1.35`.
- Install `cri-o`, `kubelet`, `kubeadm`, `kubectl`, AWS CLI, and the
  `amazon-ecr-credential-helper`.
- Disable swap and enable IPv4 forwarding.
- Use the CRI-O socket explicitly for `kubeadm init` and, when needed,
  `kubeadm join`:
  `unix:///var/run/crio/crio.sock`.
- A join token is valid for 24 hours, so the automatic join design must support
  regenerating a command.
- The worker-node tutorial policies are:
  - `AmazonEKSWorkerNodePolicy`
  - `AmazonEBSCSIDriverPolicy`
  - `AmazonEC2ContainerRegistryReadOnly`
- The control-plane API uses TCP port `6443`.
- The taught Calico manifest is version `v3.30.2`.
- Temporary external access is taught through `kubectl port-forward`.
- Plain Deployments, Services, ConfigMaps, probes, requests, limits, and
  rolling updates are the expected Kubernetes level.
- The main branch's default YOLO rolling strategy matches the course.
- The taught EBS CSI installation uses the `release-1.62` stable overlay.
- The taught StorageClass is `ebs-sc`, backed by `gp3`, with
  `WaitForFirstConsumer` and volume expansion enabled.
- Required Prometheus storage is static provisioning: an EBS volume, PV, PVC,
  and `Retain` reclaim policy.
- Dynamic EBS provisioning is taught but explicitly marked optional.
- The Prometheus example pins `prom/prometheus:v2.53.0`.
- ArgoCD is installed directly with Kubernetes manifests, not Helm.
- The tutorial uses the ArgoCD `stable` install URL.
- The taught ArgoCD manifest directory is `infra/k8s/argo/`.
- Dev automated sync uses pruning and self-healing.
- Prod intentionally has no automated sync.
- The CI workflow is taught to request `contents: write`, update the correct
  environment manifest, and commit as `github-actions[bot]`.

The Docker tutorials are not required for Task 6 planning because Task 6 reuses
the existing images and service structure rather than redesigning them.

## Approved Architecture

This section records candidates for discussion. An item does not become an
implementation decision until it is moved to the Approved Decision Log.

### Root Terraform responsibilities

- Configure AWS and Terraform versions.
- Configure the S3 backend.
- Discover exactly two available AZs.
- Discover the regional Ubuntu AMI.
- Create the VPC and two public subnets.
- Pass shared values into `modules/k8s-cluster`.

### Local cluster module responsibilities

- Create a new control-plane IAM role and instance profile and attach them to
  the new control-plane instance.
- Create a new worker IAM role and instance profile and attach them through the
  worker Launch Template.
- Add the required course policies plus the approved least-privilege S3 and
  Bedrock permissions needed by workloads on worker nodes.
- Security groups.
- Control-plane EC2 instance.
- Worker Launch Template.
- Worker Auto Scaling Group.
- SSM join parameter and narrowly scoped permissions, if SSM is approved.

### Approved worker join design

1. The control plane completes `kubeadm init`.
2. It creates a valid worker join command.
3. It stores the command in SSM Parameter Store.
4. Worker user data retries until the parameter exists.
5. The worker retrieves and runs the command.

The implemented design uses a SecureString SSM parameter, a control-plane
publisher that refreshes the 24-hour token, and a worker systemd service that
retrieves the current value again after failed join attempts and stops retrying
after success.

### Approved workspace convention

- Workspace names represent regions, for example `us-east-1`.
- They must never represent `dev` and `prod`.
- One selected regional workspace represents the one cluster.

### Approved initial access method

Use SSH tunneling or `kubectl port-forward` for the first manual validation.
Do not introduce an Ingress controller, LoadBalancer, DNS, or TLS before the
assignment/tutorial access expectation is discussed.

### Approved initial security-group direction

- SSH uses an explicitly configured allowed CIDR.
- Kubernetes API TCP 6443 is reachable from inside the VPC, not from
  `0.0.0.0/0`.
- All cluster-node traffic is allowed within the VPC CIDR.
- Normal outbound traffic is allowed for package and image downloads.

## Decisions Requiring Student Discussion

| ID | Decision | Why it matters | Status |
|---|---|---|---|
| D01 | Ubuntu AMI selection | Dynamically discover the newest matching Canonical Ubuntu x86-64 HVM/EBS server AMI in the selected region | Implemented |
| D02 | Kubernetes and CRI-O versions | Use matching stable Kubernetes v1.35 and CRI-O v1.35 package streams | Implemented |
| D03 | Calico version and pod CIDR | Use the course Calico v3.30.2 direction with kubeadm pod CIDR `192.168.0.0/16` | Bootstrap CIDR implemented; Calico remains Phase 7 |
| D04 | ArgoCD version | Follow the tutorial's direct `stable` manifest approach initially; adjust later only if required | Approved |
| D05 | Terraform/provider versions | Course specifies Terraform >=1.7.0 and AWS provider >=5.55 | Course-backed proposal |
| D06 | S3 backend bucket bootstrap | Create one dedicated versioned Terraform-state bucket once, outside the cluster configuration. Do not automate the bucket in Task 6 | Approved |
| D07 | Worker join mechanism | Use SSM Parameter Store if validation confirms it works; explain and review the mechanism before implementation | Direction approved |
| D08 | Pod S3/Bedrock permissions | Preserve service behavior using least-privilege worker instance-role permissions for Agent S3/Bedrock and YOLO S3; exact bucket/model actions remain to define | Direction approved |
| D09 | Frontend and Agent external access | Use VPC-only API access and course-taught port-forwarding initially; frontend build-time Agent URL remains a later manifest/CD detail | Initial direction approved |
| D10 | Exact ArgoCD Application list | Create dev and prod Applications for img-proc-mcp, yolo, prometheus, agent, frontend, and grafana | Approved |
| D11 | Node Exporter inclusion | Defer Node Exporter; do not add it to the initial Task 6 implementation | Approved deferment |
| D12 | Prometheus/Grafana storage scope | Use the course-taught dynamic EBS provisioning exercise for Prometheus; do not add YOLO persistence | Approved |
| D13 | Production manifest bot commit | Main requires PRs and status checks; bypass actors are not visible in the screenshot, so resolve this when implementing `cd.yaml` | Later |
| D14 | Old workflow retirement point | Old EC2 deployment must remain until Task 6 is proven | Later |
| D15 | ASG capacity operation | Keep the required min 1 and max 3, with desired >0 while working. Capacity changes are manual. If the student later parks workers at zero, the student will also handle the necessary minimum change | Approved |
| D16 | Worker compute and disk | Use `t3.medium` and 20 GiB per worker unless the instructor says otherwise | Approved |

## Proposed Terraform Module Interface — Not Yet Approved

Candidate inputs:

- `region`
- `project_name`
- `cluster_name`
- `vpc_id`
- `vpc_cidr`
- `public_subnet_ids`
- `ami_id`
- `ssh_key_name`
- `ssh_allowed_cidr`
- `control_plane_instance_type`
- `control_plane_root_volume_size`
- `worker_instance_type`
- `worker_root_volume_size`
- `worker_min_size`
- `worker_max_size`
- `worker_desired_capacity`
- `kubernetes_pod_cidr`
- `image_bucket_name`
- `bedrock_model_id`

Candidate root outputs:

- `control_plane_public_ip`
- `control_plane_private_ip`
- `control_plane_instance_id`
- `worker_asg_name`
- `vpc_id`
- `public_subnet_ids`
- `cluster_name`
- `worker_join_parameter_name`

## Proposed File Tree — Not Yet Approved

Legend:

- `[create]` new file
- `[modify]` existing file
- `[keep]` leave unchanged
- `[later]` only after the new deployment is proven
- `[decision]` depends on an unresolved choice

```text
.
├── .gitignore                                           [modify]
├── .github/
│   └── workflows/
│       ├── cluster.yaml                                 [create]
│       ├── cd.yaml                                      [create]
│       ├── test.yaml                                    [keep]
│       ├── deploy.yml                                   [later]
│       ├── deploy-agent.yml                             [later]
│       ├── deploy-frontend.yml                          [later]
│       ├── deploy-infrastructure.yml                    [later]
│       ├── deploy-mcp.yml                               [later]
│       └── deploy-yolo.yml                              [later]
├── infra/
│   ├── tf/
│   │   ├── backend.tf                                   [create]
│   │   ├── versions.tf                                  [create]
│   │   ├── providers.tf                                 [create]
│   │   ├── main.tf                                      [create]
│   │   ├── variables.tf                                 [create]
│   │   ├── outputs.tf                                   [create]
│   │   ├── tfvars/
│   │   │   └── us-east-1.tfvars                         [create]
│   │   └── modules/
│   │       └── k8s-cluster/
│   │           ├── main.tf                              [create]
│   │           ├── variables.tf                         [create]
│   │           ├── outputs.tf                           [create]
│   │           ├── control-plane-user-data.sh.tftpl     [create]
│   │           └── worker-user-data.sh.tftpl            [create]
│   └── k8s/
│       ├── addons/
│       │   ├── metrics-server/components.yaml           [keep]
│       │   └── storage-class.yaml                       [create]
│       ├── argo/
│       │   ├── img-proc-mcp-dev.yaml                    [create]
│       │   ├── img-proc-mcp-prod.yaml                   [create]
│       │   ├── yolo-dev.yaml                            [create]
│       │   ├── yolo-prod.yaml                           [create]
│       │   ├── prometheus-dev.yaml                      [create]
│       │   ├── prometheus-prod.yaml                     [create]
│       │   ├── agent-dev.yaml                           [create]
│       │   ├── agent-prod.yaml                          [create]
│       │   ├── frontend-dev.yaml                        [create]
│       │   ├── frontend-prod.yaml                       [create]
│       │   ├── grafana-dev.yaml                         [create]
│       │   └── grafana-prod.yaml                        [create]
│       ├── dev/                                         [modify later]
│       └── prod/                                        [modify later]
├── services/                                            [keep initially]
├── docker-compose.yml                                   [keep]
├── monitoring/                                          [keep]
├── task5                                                [keep]
├── task6.md                                             [keep]
└── TASK6_IMPLEMENTATION_PLAN.md                         [this file]
```

`backend.tf`, `providers.tf`, and `versions.tf` are proposed additions beyond
the assignment's minimum tree because they separate backend, provider, and
version concerns. They must be approved before creation.

The two user-data templates are proposed because long boot scripts embedded
inside Terraform resources would be harder for a student to read and test.

## Student Preparation Checklist

These are the only useful preparations before Phase 1.

- [ ] Confirm that the AWS EC2 key-pair name in `us-east-1` is exactly
  `hadi -key6`.
- [ ] Confirm that the matching private `.pem` file is still available
  privately. Do not copy it into the repository.
- [ ] Record the exact existing image bucket name used by Agent and YOLO.
- [ ] Record the exact Bedrock model ID currently used by Agent.
- [ ] Record existing GitHub secret names only; never copy their values into
  this plan.
- [ ] Choose a globally unique name for the future dedicated Terraform-state
  bucket. Do not create it until the backend preparation step is approved.
- [ ] Wait for the pending instructor clarifications.

Do not manually create the Task 6 VPC, subnets, IAM roles, security groups,
instances, Launch Template, ASG, or SSM parameter. Terraform must create those
resources so the assignment remains reproducible.

## Confirmed Existing AWS and Application Inputs

These values were confirmed by the student on 2026-07-23. They are configuration inputs; recording them does not authorize provisioning or implementation.

- AWS region currently used: `us-east-1`
- Existing AWS EC2 key-pair name: `hadi -key6`
- The matching private key is available to the student.
- Existing GitHub secrets `DEV_INSTANCE_SSH_KEY` and `PROD_INSTANCE_SSH_KEY` both contain the private key corresponding to `hadi -key6`.
- Secret-handling constraint: Codex must not read, display, copy, inspect, or commit GitHub secret values, `.pem` files, or other secret-bearing files.
- Image bucket: `hadi-polyai-images-hk2026`
- Development logs bucket: `hadi-dev-logs-bucket`
- Production logs bucket: `hadi-prod-bucket-logs`
- Application model setting: `bedrock:amazon.nova-micro-v1:0`
- Proposed Terraform state bucket name: `hadi-tf-state-bucket`

The supplied Bedrock policy permits:

- `bedrock:InvokeModel`
- `bedrock:InvokeModelWithResponseStream`

for these foundation models in any AWS region:

- `anthropic.claude-3-haiku-20240307-v1:0`
- `amazon.nova-micro-v1:0`
- `amazon.nova-lite-v1:0`
- `openai.gpt-oss-20b-1:0`
- `meta.llama3-1-8b-instruct-v1:0`
- `mistral.mistral-7b-instruct-v0:2`

The Task 6 IAM design should preserve these required Bedrock permissions for workloads running on worker nodes. The exact IAM attachment mechanism remains a Phase 1 design checkpoint and must not be implemented without phase approval.

## Ordered Implementation Phases

### Phase status

- Phase 0 — Requirements and tutorial intake: **complete**.
- Phase 1 — Terraform skeleton and regional VPC: **complete, validated, and committed** in `ea4bf2c`.
- Phase 2 — Cluster AWS resources: **implemented, validated, and committed** across `ea4bf2c` and `c791774`; the missing assignment-required managed-policy attachments found during Phase 5 review were implemented on 2026-07-24 and await validation.
- Phase 3 — Control-plane bootstrap: **complete, validated, and committed** in `ea4bf2c`.
- Phase 4 — Worker automatic join: **implemented, validated, and committed** in `c791774`. The separately approved cleanup is committed in `8ac44e6`; its Phase 5 reliability correction was implemented on 2026-07-24 and awaits validation.
- Phase 5 — Terraform validation and reviewed plan: **in progress**. AWS identity, region, backend bucket, backend initialization, and the selected `us-east-1` workspace are confirmed. Pre-plan IAM and stale-cleanup corrections are implemented and await formatting/validation; the first saved Terraform plan has not been created or reviewed.
- Phases 6–14: **not approved and not started**.
- Provisioning status: no `terraform apply` has run and no cluster resources have been provisioned.

The student approved `ssh_ingress_cidr = "0.0.0.0/0"` as a temporary,
course-compatible rule so GitHub-hosted runners can reach SSH. This exposes
port 22 to connection attempts from the internet; key authentication remains
required. Revisit and restrict or replace this rule when the GitHub Actions
connection design is reviewed.

### Worker lifecycle clarification

- Automatic worker joining is required. A one-time `kubeadm` join command and
  manual token renewal are not acceptable as the final design.
- Phase 4 must teach and review the token-refresh mechanism before it is
  implemented. The current preferred design is for the control plane to
  periodically generate a fresh, time-limited join command and overwrite a
  protected SSM Parameter Store value; workers retrieve the current value at
  boot.
- The control-plane refresh service must also run after every control-plane
  boot, not only on a wall-clock schedule. Its `systemd` timer should use
  `Persistent=true`, an `OnBootSec` trigger, and a recurring trigger.
- Worker joining must be a retrying `systemd` service rather than a one-shot
  cloud-init command. Each retry must fetch the current SSM value again, so a
  worker waiting while the control plane is stopped can join after the control
  plane restarts and publishes a fresh token.
- A non-expiring `kubeadm` token is not the preferred design because it avoids
  renewal by leaving a long-lived cluster bootstrap credential valid.
- Automatic cleanup of confirmed stale Kubernetes Node objects is the current
  student-approved direction.
- Cleanup must be associated with a confirmed worker/ASG termination and must
  not delete nodes merely because they temporarily report `NotReady`.
- The implemented control-plane timer maps each Kubernetes worker's internal IP
  to EC2 state and deletes only confirmed stale records. Keep the mechanism
  isolated so it can be changed back to documented manual cleanup if the
  instructor says automation is outside Task 6 scope.

### GitHub and Argo CD automation decision

- GitHub OIDC is deferred and is not part of the initial Task 6 implementation.
- Application CI builds and pushes container images, then updates the matching
  Kubernetes manifest image reference in Git.
- Argo CD observes the committed manifest change and synchronizes it into the
  appropriate `dev` or `prod` namespace; routine application deployment does
  not SSH into worker nodes.
- The cluster bootstrap workflow is separate. It may use the existing SSH
  private-key GitHub secret to connect to the control plane for initial
  cluster-level setup required by Task 6.
- For the initial course-scoped implementation, Terraform outputs the current
  control-plane public IP and the student stores it in a GitHub variable used
  by `cluster.yaml`. If the instance is stopped and restarted, that variable
  must be updated. Dynamic AWS API discovery can replace this later without
  changing the cluster architecture.

### Phase 0 — Requirements and tutorial intake

Status: **complete**

- [x] Read `task6.md`.
- [x] Read `task5`.
- [x] Read `tf_modules.md`.
- [x] Read course tutorials 35–42.
- [x] Read the current repository.
- [x] Compare `main`, `dev`, and the Task 6 feature branch.
- [x] Confirm that the feature branch is identical to `main`.
- [x] Record repository gaps.
- [x] Add/read the relevant Kubernetes and Terraform tutorials.
- [x] Resolve decisions required before Terraform implementation.
- [x] Approve the Terraform architecture and implemented Phase 1–4 file tree.

Deliverable: approved decision log and finalized plan only.

### Phase 1 — Terraform skeleton and regional VPC

Status: **complete — validated and committed**

- Add Terraform ignore patterns.
- Create the approved `infra/tf/` structure.
- Add version/provider/backend declarations.
- Add root variables and `us-east-1.tfvars`.
- Discover the regional AMI and accept exactly two regional AZ values from the
  selected `.tfvars` file.
- Create the VPC and two public subnets with the taught module.
- Declare the local cluster module call/interface.

Validation is static only. Do not provision.

### Phase 2 — Cluster AWS resources

Status: **implemented and committed — Phase 5 IAM correction pending**

- Create IAM roles and instance profiles.
- Create security groups.
- Create the control-plane EC2 resource.
- Create the worker Launch Template.
- Create the worker ASG.
- Create approved outputs.

Validation is static only. Do not provision.

### Phase 3 — Control-plane bootstrap

Status: **complete — validated and committed**

- Implement deterministic package installation.
- Configure kernel modules and sysctl.
- Install/configure the course's CRI-O packages without installing Docker.
- Install the approved Kubernetes v1.35 packages.
- Disable swap and enable IPv4 forwarding.
- Run guarded `kubeadm init` with the CRI-O socket.
- Write useful bootstrap logs.

### Phase 4 — Worker automatic join

Status: **implemented and committed — Phase 5 cleanup correction pending**

- Implement the approved join mechanism.
- Add scoped IAM.
- Retry only while the node is unjoined; stop after a successful join.
- Handle the course-documented 24-hour token lifetime and recreation.
- Automatically remove only Node records whose matching EC2 instance is
  confirmed by AWS as `terminated`; never delete solely because a node is
  temporarily `NotReady`.

The automatic cleanup was separately approved and committed. It is a periodic
control-plane check, not an ASG lifecycle hook.

### Phase 5 — Terraform validation and reviewed plan

Status: **in progress — plan creation/review not yet approved**

- Student runs formatting and validation commands.
- Correct assignment-required IAM attachment gaps found during pre-plan review.
- Correct the stale-worker cleanup timing gap found during pre-plan review.
- Review the exact Terraform plan.
- Confirm AWS account, region, workspace, resource names, and expected cost.

### Phase 6 — First approved provisioning

Status: **not approved**

- Apply only the reviewed plan.
- Verify cloud-init and kubeadm.
- Verify the control plane and worker join.

### Phase 7 — Manual Task 6 Part II

Status: **not approved**

- Manually install Calico.
- Manually install ArgoCD.
- Manually install the EBS CSI driver and required Prometheus storage.
- Retrieve the initial password.
- Manually create Applications.
- Verify dev automatic sync and prod manual sync.

This phase must succeed before automating bootstrap.

### Phase 8 — Manifest compatibility fixes

Status: **not approved**

- Fix only confirmed blockers in existing Task 5 manifests.
- Resolve AWS access.
- Resolve frontend/agent access.
- Replace hardcoded EBS/AZ assumptions.
- Replace static Prometheus PVs and hardcoded EBS IDs with the approved
  dynamic-provisioning design: EBS CSI driver, `ebs-sc`, and Prometheus PVC.
- Do not add durable YOLO storage unless a later requirement explicitly asks
  for it.
- Handle secrets safely.
- Resolve Node Exporter scope.

### Phase 9 — ArgoCD Application files

Status: **not approved**

- Create one approved Application per required service and environment.
- Dev targets `dev` with auto-sync.
- Prod targets `main` with manual sync.

### Phase 10 — `cluster.yaml`

Status: **not approved**

- Automate the already-proven Terraform and bootstrap procedures.
- Validate region input.
- Obtain the control-plane IP from Terraform output.
- Use readiness polling instead of arbitrary sleeps.
- Keep bootstrap idempotent.

### Phase 11 — `cd.yaml`

Status: **not approved**

- Detect changed buildable services.
- Build and push only affected Docker Hub images.
- Update only the matching environment manifest.
- Commit the manifest update safely.
- Prevent infinite workflow loops.
- Preserve production manual ArgoCD sync.

### Phase 12 — Non-destructive end-to-end validation

Status: **not approved**

- Validate Terraform, scripts, manifests, Applications, and workflows.
- Confirm README-only changes do not rebuild services.
- Confirm one service change updates only that service.
- Confirm dev auto-syncs.
- Confirm prod remains waiting for manual sync.

### Phase 13 — Clean destroy/recreate test

Status: **not approved; destructive approval required**

- Confirm exact AWS account, region, workspace, state, and destroy plan.
- Confirm old manual Task 5 resources are outside Terraform state.
- Destroy only Task 6-managed resources.
- Recreate through `cluster.yaml`.
- Verify the full stack.

### Phase 14 — Old workflow/infrastructure retirement

Status: **not approved**

- Decide which old workflows become obsolete.
- Retire the old development and production EC2 instances and their Elastic
  IPs only after Task 6 is fully proven and the student explicitly approves
  the exact removal targets.

## Approved Decision Log

| Date | ID | Decision | Reason |
|---|---|---|---|
| 2026-07-23 | A01 | Initial deployment region is `us-east-1` | This is the student's normal course region |
| 2026-07-23 | A02 | Two subnets belong to two AZs inside one region | This is the explicit Task 6 requirement |
| 2026-07-23 | A03 | Preserve old Task 5 infrastructure | Explicit Task 5 and Task 6 working rule |
| 2026-07-23 | A04 | Planning file may be created | Explicit student approval |
| 2026-07-23 | A05 | Use VPC module version `5.8.1`, regional `.tfvars` AZ inputs, and regional AMI discovery | Keeps the reusable module portable while making the two selected AZs explicit |
| 2026-07-23 | A06 | Require exactly two different AZ values in each regional `.tfvars` file | Task 6 requires exactly two public subnets in different AZs |
| 2026-07-23 | A07 | Do not add durable YOLO storage as Task 6 scope | Instructor allowed it to remain deferred in Task 5 |
| 2026-07-23 | A08 | Retire old EC2 instances and EIPs only after the replacement is verified | Prevents removing the working deployment prematurely |
| 2026-07-23 | A09 | Use dynamic EBS provisioning for Prometheus | It is taught in `k8s_data_persistence.md` and supports automatic recreation without hardcoded EBS IDs |
| 2026-07-23 | A10 | Worker instances use `t3.medium` with 20 GiB root volumes | Student selection pending any instructor correction |
| 2026-07-23 | A11 | Scaling is manual through Terraform ASG capacity values; launched workers join automatically | Matches the Task 6 learning objective |
| 2026-07-23 | A12 | Keep API port 6443 VPC-only and use restricted SSH ingress | Workers and on-node kubectl need API access; public API exposure is unnecessary |
| 2026-07-23 | A13 | Create dev/prod ArgoCD Applications for six workloads and defer Node Exporter | Explicit student selection |
| 2026-07-23 | A14 | Install ArgoCD from the tutorial's direct `stable` manifest URL initially | Student chose to follow the taught approach and adjust later only if needed |
| 2026-07-23 | A15 | Keep ASG minimum and desired capacity at one initially; scale upward manually | Student does not want a zero-worker mode |
| 2026-07-23 | A16 | Use SSM Parameter Store as the worker-join candidate, with an explanation checkpoint before implementation | Student wants to learn the mechanism while implementing it |
| 2026-07-23 | A17 | Preserve Agent and YOLO AWS behavior through least-privilege worker IAM permissions | Avoids application redesign and committed long-lived AWS credentials |
| 2026-07-23 | A18 | Create the dedicated versioned Terraform-state bucket once and do not automate it in Task 6 | Matches the course backend bootstrap flow and avoids a second Terraform root |
| 2026-07-23 | A19 | Keep ASG min 1/max 3 and desired capacity greater than zero while working; scaling decisions remain manual | Follows the exact Task 6 operating model |
| 2026-07-23 | A20 | Terraform creates and attaches new cluster IAM roles instead of reusing roles attached to old EC2 deployments | Keeps Task 6 reproducible and prevents coupling to infrastructure that will later be retired |
| 2026-07-23 | A21 | Existing bucket names and region values are non-secret configuration and will be supplied to Kubernetes workloads automatically through committed manifests | Preserves current application environment-variable contracts without manual pod configuration |
| 2026-07-23 | A22 | Discover an Ubuntu AMI regionally without hardcoding an AMI ID or treating a tutorial release example as a requirement | Matches Task 6 portability; exact required filters will be reviewed in Phase 1 |
| 2026-07-23 | A23 | The existing AWS key-pair name is exactly `hadi -key6`, including the space | Student confirmed the AWS-side key-pair name |

## Progress Log

### 2026-07-23

- Read the authoritative Task 6 assignment.
- Read the authoritative Task 5 assignment.
- Read `tf_modules.md` and recorded its course-backed module conventions.
- Read the complete tutorial set for lessons 35–42.
- Recorded Kubernetes v1.35, Calico v3.30.2, EBS CSI release-1.62,
  Prometheus v2.53.0, Terraform >=1.7.0, and AWS provider >=5.55 as the
  course-backed versions.
- Replaced proposed vendored Calico/ArgoCD files with the course's direct
  installation approach.
- Changed the proposed ArgoCD directory to the taught `infra/k8s/argo/`.
- Selected the course-taught dynamic EBS provisioning exercise for Prometheus.
- Selected `t3.medium`/20 GiB workers and manual desired-capacity scaling.
- Selected VPC-only Kubernetes API access.
- Selected twelve initial ArgoCD Applications: dev/prod for six workloads.
- Deferred Node Exporter.
- Selected the tutorial's direct ArgoCD `stable` manifest installation for the
  initial implementation.
- Removed zero-worker mode from the plan: keep one worker and scale upward
  manually through desired capacity.
- Selected SSM Parameter Store as the worker-join candidate with a teaching
  checkpoint before implementation.
- Selected worker instance-role permissions as the initial way to preserve
  Agent S3/Bedrock and YOLO S3 access without changing their code structure.
- Removed Terraform automation for the state-backend bucket; it will be a
  one-time dedicated versioned bucket.
- Restored the ASG wording to the exact Task 6 model: min 1, max 3, desired
  greater than zero while working, with manual capacity changes.
- Removed the accidental Ubuntu-release and “preferred architecture” decision.
  Phase 1 will use only the regional Ubuntu data-source filters technically
  required by Task 6 and the selected `t3.medium` instance.
- Recorded the existing AWS key-pair name as `hadi -key6`.
- Recorded that the visible `main` rules require pull requests and status
  checks; the workflow-bypass configuration remains unknown.
- Confirmed that multi-AZ does not mean multi-region.
- Confirmed that region portability uses provider variables, matching tfvars,
  workspaces, dynamic AZs, and a regional AMI data source.
- Recorded that YOLO persistence is outside the current required scope.
- Recorded that old EC2 instances and EIPs are retirement-phase resources.
- Refreshed the baseline after the Task 5 pull requests were merged.
- Confirmed that `feature/kubernetes-cluster-provisioning-as-code` is identical
  to `main` at commit `9ae78e4`.
- Documented the three non-authoritative local `dev` differences: YOLO
  `Recreate`, old systemd units, and a duplicate Python import.
- Confirmed that the branch comparison does not require a Task 6 architecture
  change.
- Completed the initial repository audit.
- Created this plan and tracker with no infrastructure or code implementation.

## Next Recommended Approval

Approve only the remaining part of **Phase 5 — Terraform validation and
reviewed plan**:

1. confirm the selected workspace is still `us-east-1`;
2. create a saved Terraform plan using `regions/us-east-1.tfvars`;
3. inspect the complete plan for expected additions, names, region, counts,
   IAM permissions, and cost-driving resources;
4. make no infrastructure changes.

`terraform apply` is Phase 6 and remains separately unapproved.
