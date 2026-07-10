# Terraform: GKE Autopilot for Rehearse

Provisions one Autopilot cluster to run the Helm chart on real cloud. Meant to be brought
up for a demo and torn down after, so it stays inside the GCP free trial and costs about
nothing.

## Bring up

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # set your project_id
gcloud auth application-default login
terraform init
terraform plan                                 # read the plan before you apply
terraform apply
$(terraform output -raw get_credentials)       # point kubectl at the cluster
```

Then deploy the app with the Helm chart (see the repo README, Kubernetes section).

## Tear down (do this when you're done)

```bash
terraform destroy
```

## Cost

Autopilot bills for the resources your pods request, and GCP waives the management fee on
the first cluster. Inside the $300 / 90-day free trial a short-lived demo is effectively
free. Don't leave it running: an idle cluster still bills for whatever is scheduled on it.
State is local (terraform.tfstate, gitignored); fine for a single operator.
