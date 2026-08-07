resource "aws_security_group" "alb" {
  name        = "${var.project_name}-${terraform.workspace}-alb"
  description = "Allow HTTPS inbound from the internet; allow NodePort traffic to cluster"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description = "HTTPS from internet"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "NodePort traffic to cluster instances"
    from_port   = 30000
    to_port     = 32767
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  tags = {
    Name = "${var.display_name_prefix}-${terraform.workspace}-alb"
  }
}

resource "aws_lb" "this" {
  # ALB name max 32 chars.
  # display_name_prefix ("hadi-polyai" = 11) + "-" + workspace ("us-east-1" = 9) = 21 chars — safe.
  name               = "${var.display_name_prefix}-${terraform.workspace}"
  load_balancer_type = "application"
  internal           = false
  subnets            = module.vpc.public_subnets
  security_groups    = [aws_security_group.alb.id]

  tags = {
    Name = "${var.display_name_prefix}-${terraform.workspace}-alb"
  }
}

resource "aws_lb_target_group" "this" {
  name        = "${var.display_name_prefix}-${terraform.workspace}"
  port        = 30080
  protocol    = "HTTP"
  target_type = "instance"
  vpc_id      = module.vpc.vpc_id

  health_check {
    enabled = true
    # Port 10254 (NodePort 31254) is the ingress-nginx controller's own healthz
    # server; it returns HTTP 200 on /healthz when the controller is ready.
    # Port 30080 returns 404 for unknown hosts and is not suitable for health checks.
    port                = "31254"
    path                = "/healthz"
    protocol            = "HTTP"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 15
    timeout             = 5
    matcher             = "200"
  }

  tags = {
    Name = "${var.display_name_prefix}-${terraform.workspace}-tg"
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate_validation.this.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.this.arn
  }
}

resource "aws_autoscaling_attachment" "this" {
  autoscaling_group_name = aws_autoscaling_group.worker.name
  lb_target_group_arn    = aws_lb_target_group.this.arn
}

resource "aws_route53_record" "services" {
  for_each = toset(local.service_fqdns)

  zone_id = data.aws_route53_zone.fursa_click.zone_id
  name    = each.key
  type    = "A"

  alias {
    name                   = aws_lb.this.dns_name
    zone_id                = aws_lb.this.zone_id
    evaluate_target_health = true
  }
}
