locals {
  service_names = [
    "frontend",
    "frontend-dev",
    "agent",
    "agent-dev",
    "grafana",
    "prometheus",
    "argocd",
  ]

  dns_subdomain = var.display_name_prefix # "hadi-polyai"

  service_fqdns = [
    for s in local.service_names :
    "${s}.${local.dns_subdomain}.${var.route53_zone_name}"
  ]
}

data "aws_route53_zone" "fursa_click" {
  name         = "${var.route53_zone_name}."
  private_zone = false
}

resource "aws_acm_certificate" "this" {
  domain_name               = local.service_fqdns[0]
  subject_alternative_names = slice(local.service_fqdns, 1, length(local.service_fqdns))
  validation_method         = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.this.domain_validation_options :
    dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  zone_id = data.aws_route53_zone.fursa_click.zone_id
  name    = each.value.name
  type    = each.value.type
  records = [each.value.record]
  ttl     = 60
}

resource "aws_acm_certificate_validation" "this" {
  certificate_arn         = aws_acm_certificate.this.arn
  validation_record_fqdns = [for r in aws_route53_record.cert_validation : r.fqdn]
}
