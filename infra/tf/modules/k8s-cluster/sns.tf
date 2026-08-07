resource "aws_sns_topic" "alerts" {
  name = "${var.project_name}-${terraform.workspace}-alerts"

  tags = {
    Name = "${var.display_name_prefix}-${terraform.workspace}-alerts"
  }
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alertmanager_email
}

resource "aws_iam_role_policy" "worker_sns_publish" {
  name = "${var.project_name}-${terraform.workspace}-sns-publish"
  role = aws_iam_role.worker.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "PublishAlerts"
      Effect   = "Allow"
      Action   = ["sns:Publish"]
      Resource = aws_sns_topic.alerts.arn
    }]
  })
}
