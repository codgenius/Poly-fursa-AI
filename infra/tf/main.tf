module "k8s_cluster" {
  source = "./modules/k8s-cluster"

  project_name                = var.project_name
  aws_region                  = var.aws_region
  vpc_cidr                    = var.vpc_cidr
  availability_zones          = var.availability_zones
  public_subnet_cidrs         = var.public_subnet_cidrs
  ssh_key_name                = var.ssh_key_name
  ssh_ingress_cidr            = var.ssh_ingress_cidr
  control_plane_instance_type = var.control_plane_instance_type
  control_plane_volume_size   = var.control_plane_volume_size
  worker_instance_type        = var.worker_instance_type
  worker_volume_size          = var.worker_volume_size
  worker_min_size             = var.worker_min_size
  worker_max_size             = var.worker_max_size
  worker_desired_capacity     = var.worker_desired_capacity
  image_bucket_name           = var.image_bucket_name
  bedrock_model_arns          = var.bedrock_model_arns
}
