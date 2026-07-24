aws_region = "us-east-1"

project_name = "polyai"
vpc_cidr     = "10.0.0.0/16"

availability_zones = [
  "us-east-1a",
  "us-east-1b",
]

public_subnet_cidrs = [
  "10.0.0.0/24",
  "10.0.1.0/24",
]

ssh_key_name     = "hadi -key6"
ssh_ingress_cidr = "0.0.0.0/0"

control_plane_instance_type = "t3.medium"
control_plane_volume_size   = 20

worker_instance_type    = "t3.medium"
worker_volume_size      = 20
worker_min_size         = 1
worker_max_size         = 3
worker_desired_capacity = 1

image_bucket_name = "hadi-polyai-images-hk2026"

bedrock_model_arns = [
  "arn:aws:bedrock:*::foundation-model/anthropic.claude-3-haiku-20240307-v1:0",
  "arn:aws:bedrock:*::foundation-model/amazon.nova-micro-v1:0",
  "arn:aws:bedrock:*::foundation-model/amazon.nova-lite-v1:0",
  "arn:aws:bedrock:*::foundation-model/openai.gpt-oss-20b-1:0",
  "arn:aws:bedrock:*::foundation-model/meta.llama3-1-8b-instruct-v1:0",
  "arn:aws:bedrock:*::foundation-model/mistral.mistral-7b-instruct-v0:2",
]
