"""A tiny Kubernetes operator for running evals as a custom resource.

The idea: treat "score the golden set" as something the cluster manages, not a script you
run by hand. You apply an EvalRun object, the operator turns it into a Kubernetes Job that
runs the eval, and when the Job finishes the operator reads the result out of the pod logs
and writes it back onto the EvalRun's status. So `kubectl get evalruns` shows you the QWK.

The eval it runs is the offline one (eval.emit_agreement) so a demo needs no API key and
gives the same frozen number every time. Swapping in the live eval is just a different
command on the Job.

Runs via kopf:  kopf run --standalone rehearse_operator/main.py
"""

import json
import os
import time

import kopf
import kubernetes

GROUP = "rehearse.dev"
VERSION = "v1alpha1"
PLURAL = "evalruns"
LABEL = "rehearse.dev/evalrun"  # ties a Job back to the EvalRun that spawned it

# The image the eval Job runs. Same image as the operator/API; the chart sets this.
EVAL_IMAGE = os.environ.get("EVAL_IMAGE", "ghcr.io/mitalipurwar21/rehearse:latest")


@kopf.on.startup()
def load_kube_config(**_):
    # In-cluster when deployed; fall back to the local kubeconfig for `kopf run` on a laptop.
    try:
        kubernetes.config.load_incluster_config()
    except kubernetes.config.ConfigException:
        kubernetes.config.load_kube_config()


def _eval_job(name: str) -> dict:
    job_name = f"evalrun-{name}-{int(time.time())}"
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": job_name, "labels": {LABEL: name}},
        "spec": {
            "backoffLimit": 1,
            "ttlSecondsAfterFinished": 600,  # let it linger briefly so you can read logs
            "template": {
                "metadata": {"labels": {LABEL: name}},
                "spec": {
                    "restartPolicy": "Never",
                    "containers": [
                        {
                            "name": "eval",
                            "image": EVAL_IMAGE,
                            "command": ["python", "-m", "eval.emit_agreement"],
                            "resources": {
                                "requests": {"cpu": "100m", "memory": "256Mi"},
                                "limits": {"cpu": "500m", "memory": "512Mi"},
                            },
                        }
                    ],
                },
            },
        },
    }


@kopf.on.create(GROUP, VERSION, PLURAL)
def start_eval(name, namespace, patch, logger, **_):
    job = _eval_job(name)
    kopf.adopt(job)  # owner ref -> deleting the EvalRun cleans up the Job too
    kubernetes.client.BatchV1Api().create_namespaced_job(namespace, job)
    patch.status["phase"] = "Running"
    patch.status["jobName"] = job["metadata"]["name"]
    logger.info(f"launched {job['metadata']['name']} for EvalRun {name}")


@kopf.on.event("batch", "v1", "jobs", labels={LABEL: kopf.PRESENT})
def on_job_event(event, namespace, labels, logger, **_):
    # Fires whenever a Job we own changes. Once it's done, copy the outcome onto the
    # EvalRun that spawned it. Ignore the noisy in-progress events.
    job = event["object"]
    status = job.get("status", {})
    evalrun = labels[LABEL]
    if status.get("succeeded"):
        result = _read_result(namespace, job["metadata"]["name"], logger)
        _patch_status(namespace, evalrun, {"phase": "Succeeded", **result})
        logger.info(f"EvalRun {evalrun} succeeded: {result}")
    elif status.get("failed"):
        _patch_status(namespace, evalrun, {"phase": "Failed", "message": "eval Job failed"})
        logger.warning(f"EvalRun {evalrun} failed")


def _read_result(namespace: str, job_name: str, logger) -> dict:
    # The Job prints one JSON line. Read the pod log RAW (_preload_content=False): our log
    # is pure JSON, and the client otherwise runs it through json.loads and hands back a
    # single-quoted Python repr that won't parse. Retry a bit since the log can lag the Job
    # reporting success, and scan bottom-up for the line with a qwk.
    core = kubernetes.client.CoreV1Api()
    for _ in range(15):
        pods = core.list_namespaced_pod(namespace, label_selector=f"job-name={job_name}")
        for pod in pods.items:
            try:
                resp = core.read_namespaced_pod_log(
                    pod.metadata.name, namespace, container="eval", _preload_content=False
                )
                log = resp.read().decode("utf-8")
            except kubernetes.client.ApiException:
                continue
            for line in reversed(log.splitlines()):
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    data = json.loads(line)
                except ValueError:
                    continue
                if "qwk" in data:
                    return {"qwk": data["qwk"], "nPairs": data["n_pairs"]}
        time.sleep(1)
    logger.warning("no agreement JSON found in the job logs")
    return {"message": "result unreadable"}


def _patch_status(namespace: str, evalrun: str, status: dict) -> None:
    kubernetes.client.CustomObjectsApi().patch_namespaced_custom_object_status(
        GROUP, VERSION, namespace, PLURAL, evalrun, {"status": status}
    )
