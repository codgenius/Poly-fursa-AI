data "aws_caller_identity" "current" {}

data "aws_partition" "current" {}

# A local value is a reusable calculated value, not a shell command.
# The workspace keeps each regional cluster's SSM parameter name separate.
locals {
  join_command_parameter_name = "/${var.project_name}/${terraform.workspace}/kubeadm-join-command"
}

# A data aws_iam_policy_document block only builds and validates an IAM policy
# JSON document. It does not create or attach an AWS policy by itself.
data "aws_iam_policy_document" "control_plane_ssm_publish" {
  statement {
    sid     = "PublishWorkerJoinCommand"
    effect  = "Allow"
    actions = ["ssm:PutParameter"]
    resources = [
      "arn:${data.aws_partition.current.partition}:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter${local.join_command_parameter_name}",
    ]
  }
}

# This resource takes the JSON document above and attaches it as an inline
# policy to the control-plane role created in main.tf.
resource "aws_iam_role_policy" "control_plane_ssm_publish" {
  name   = "${var.project_name}-${terraform.workspace}-publish-join-command"
  role   = aws_iam_role.control_plane.id
  policy = data.aws_iam_policy_document.control_plane_ssm_publish.json
}

data "aws_iam_policy_document" "control_plane_worker_lookup" {
  statement {
    sid       = "InspectWorkerInstanceState"
    effect    = "Allow"
    actions   = ["ec2:DescribeInstances"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "control_plane_worker_lookup" {
  name   = "${var.project_name}-${terraform.workspace}-inspect-workers"
  role   = aws_iam_role.control_plane.id
  policy = data.aws_iam_policy_document.control_plane_worker_lookup.json
}

# The single EC2 control-plane instance. Its user-data template installs and
# initializes Kubernetes automatically during the instance's first boot.
resource "aws_instance" "control_plane" {
  ami                         = data.aws_ami.ubuntu.id
  instance_type               = var.control_plane_instance_type
  subnet_id                   = module.vpc.public_subnets[0]
  associate_public_ip_address = true
  key_name                    = var.ssh_key_name
  vpc_security_group_ids      = [aws_security_group.cluster.id]
  iam_instance_profile        = aws_iam_instance_profile.control_plane.name

  user_data = templatefile("${path.module}/templates/control-plane-user-data.sh.tftpl", {
    aws_region               = var.aws_region
    ssm_parameter_name       = local.join_command_parameter_name
    kubernetes_minor_version = "v1.35"
    crio_minor_version       = "v1.35"
    pod_network_cidr         = "192.168.0.0/16"
  })

  user_data_replace_on_change = true

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  root_block_device {
    encrypted   = true
    volume_size = var.control_plane_volume_size
    volume_type = "gp3"
  }

  tags = {
    Name = "${var.project_name}-${terraform.workspace}-control-plane"
    Role = "control-plane"
  }

  depends_on = [
    aws_iam_role_policy.control_plane_ssm_publish,
    aws_iam_role_policy.control_plane_worker_lookup,
    aws_iam_role_policy_attachment.control_plane_ssm,
  ]
}
