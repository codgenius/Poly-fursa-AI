data "aws_iam_policy_document" "worker_ssm_join" {
  statement {
    sid     = "ReadWorkerJoinCommand"
    effect  = "Allow"
    actions = ["ssm:GetParameter"]
    resources = [
      "arn:${data.aws_partition.current.partition}:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter${local.join_command_parameter_name}",
    ]
  }
}

resource "aws_iam_role_policy" "worker_ssm_join" {
  name   = "${var.project_name}-${terraform.workspace}-read-join-command"
  role   = aws_iam_role.worker.id
  policy = data.aws_iam_policy_document.worker_ssm_join.json
}

resource "aws_launch_template" "worker" {
  name_prefix   = "${var.project_name}-${terraform.workspace}-worker-"
  image_id      = data.aws_ami.ubuntu.id
  instance_type = var.worker_instance_type
  key_name      = var.ssh_key_name

  update_default_version = true

  iam_instance_profile {
    name = aws_iam_instance_profile.worker.name
  }

  vpc_security_group_ids = [aws_security_group.cluster.id]

  user_data = base64encode(templatefile("${path.module}/templates/worker-user-data.sh.tftpl", {
    aws_region               = var.aws_region
    ssm_parameter_name       = local.join_command_parameter_name
    kubernetes_minor_version = "v1.35"
    crio_minor_version       = "v1.35"
  }))

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  block_device_mappings {
    device_name = "/dev/sda1"

    ebs {
      delete_on_termination = true
      encrypted             = true
      volume_size           = var.worker_volume_size
      volume_type           = "gp3"
    }
  }

  tag_specifications {
    resource_type = "instance"

    tags = {
      Name = "${var.project_name}-${terraform.workspace}-worker"
      Role = "worker"
    }
  }

  tag_specifications {
    resource_type = "volume"

    tags = {
      Name = "${var.project_name}-${terraform.workspace}-worker"
    }
  }

  depends_on = [
    aws_iam_role_policy.worker_application_access,
    aws_iam_role_policy.worker_ssm_join,
    aws_iam_role_policy_attachment.worker_ebs_csi,
    aws_iam_role_policy_attachment.worker_ecr_read,
    aws_iam_role_policy_attachment.worker_eks,
    aws_iam_role_policy_attachment.worker_ssm,
  ]
}

resource "aws_autoscaling_group" "worker" {
  name                = "${var.project_name}-${terraform.workspace}-worker"
  min_size            = var.worker_min_size
  max_size            = var.worker_max_size
  desired_capacity    = var.worker_desired_capacity
  vpc_zone_identifier = module.vpc.public_subnets

  health_check_type         = "EC2"
  health_check_grace_period = 600

  launch_template {
    id      = aws_launch_template.worker.id
    version = "$Latest"
  }

  tag {
    key                 = "Name"
    value               = "${var.project_name}-${terraform.workspace}-worker"
    propagate_at_launch = true
  }

  tag {
    key                 = "Role"
    value               = "worker"
    propagate_at_launch = true
  }
}
