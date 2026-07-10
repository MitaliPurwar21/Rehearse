variable "project_id" {
  description = "GCP project id to create the cluster in"
  type        = string
}

variable "region" {
  description = "GCP region for the Autopilot cluster"
  type        = string
  default     = "us-central1"
}

variable "cluster_name" {
  description = "Name of the GKE cluster"
  type        = string
  default     = "rehearse"
}
