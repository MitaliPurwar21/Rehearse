# One GKE Autopilot cluster. Autopilot bills per running pod and waives the management
# fee on the first cluster, so within the GCP free trial this costs about nothing, and
# `terraform destroy` takes it all away when you're done. deletion_protection is off on
# purpose so a demo cluster is easy to tear down.
resource "google_container_cluster" "rehearse" {
  name             = var.cluster_name
  location         = var.region
  enable_autopilot = true

  deletion_protection = false
}
