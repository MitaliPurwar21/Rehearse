output "cluster_name" {
  value = google_container_cluster.rehearse.name
}

output "region" {
  value = var.region
}

# Copy-paste this to point kubectl at the new cluster.
output "get_credentials" {
  value = "gcloud container clusters get-credentials ${google_container_cluster.rehearse.name} --region ${var.region} --project ${var.project_id}"
}
