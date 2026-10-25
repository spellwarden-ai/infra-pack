---
name: kubernetes-incident-triage
description: Triage a Kubernetes workload, node or cluster problem from command output, events, logs and manifests. Use it when pods are missing, Pending, crashing, not Ready, evicted or stuck, when a Deployment, StatefulSet, DaemonSet, Job or CronJob misbehaves, when nodes, volumes, networking or certificates fail, or when someone proposes deleting, restarting, scaling or relaxing something to make an incident go away. It reads the states of pods, nodes and controllers, finds the cause the evidence supports, chooses the least disruptive next step, and recognises actions that lose data or availability.
license: Apache-2.0
metadata:
  version: "0.9.0"
  author: Spellwarden
---

# Kubernetes incident triage

Work from the evidence to the cause, then to the smallest step that fixes it. A symptom often shows on one object while its cause is recorded on another, so follow the chain: controller (Deployment, StatefulSet, DaemonSet, Job, CronJob), then its ReplicaSet or Job, the pod, the container, and the node and volumes under it.

## Read the state

Where the failure shows says where to look:

- A controller with no pods at all: pods are refused at creation. Read the events of the ReplicaSet, StatefulSet or Job (`FailedCreate`): admission (Pod Security, a policy engine or webhook), ResourceQuota or LimitRange, a missing service account.
- `Pending`: the scheduler cannot place the pod. Its events name the reason: requests larger than any node has free, taints without tolerations, affinity or topology rules, or a PersistentVolumeClaim that is unbound or bound to a volume in another zone.
- `ContainerCreating` for minutes: a volume that will not attach or mount, a missing Secret or ConfigMap, the network plugin.
- `ErrImagePull` or `ImagePullBackOff`: wrong image name or tag, a missing pull secret, an unreachable or rate-limited registry.
- `CrashLoopBackOff`: the container starts and exits. Read `kubectl logs --previous` and `lastState.terminated` (`reason`, `exitCode`). Exit 137 with `OOMKilled` is the memory limit; 137 without it is a SIGKILL, often after failed liveness probes; 143 is SIGTERM; 1 or another code is the program's own error.
- `Running` but not Ready: the readiness probe fails, and Services send it no traffic.
- `Terminating` for a long time: a finalizer, or a node that stopped responding. `Evicted`: node pressure on memory, disk or process IDs.
- A node `NotReady` or under pressure: kubelet, container runtime, disk or network on that node; read its conditions and events.

Events are kept only about an hour by default, so no event is not proof that nothing happened; logs and metrics fill the gap.

## Find the cause the evidence supports

- Separate what the output shows from what it suggests. Build a short timeline (first error, first restart, the change just before it: rollout, config, node, upstream). The latest error is often a consequence of an earlier one.
- Before reversing a state someone set (replicas at zero, a cordoned node, a suspended CronJob, a paused rollout, a removed label), find who set it and why: the object's `managedFields` (manager and time of each field), `kubectl rollout history`, the API server audit log, the GitOps history and the incident channel. A deliberate stop to contain damage looks just like an outage, and undoing it can restart the damage. Check also for an autoscaler or GitOps controller that would revert a manual change.
- Compare the failing object with one that works (the previous ReplicaSet, another replica, another namespace) and find the difference.
- A trust error (`x509: certificate signed by unknown authority`) means client and server disagree on the chain: compare the issuer chain the server presents with the CA bundle the pod mounts, and check the dates of both. An expired certificate shows in `notAfter`.
- A Service with no endpoints: its selector does not match the pods' labels, the pods are not Ready, or `targetPort` is wrong. A NetworkPolicy that selects a pod denies, in the directions its `policyTypes` name, the traffic it does not allow (an empty `podSelector` selects every pod in the namespace).
- Environment variables from a ConfigMap or Secret are fixed when the container starts. Mounted files are refreshed in the running pod after a short delay, never for a `subPath` mount, and a program that loads a file only at start still needs a restart to use the new content.
- When the inputs cannot tell causes apart, say which ones remain and the one check that separates them.

## Choose the least disruptive step

Order: read-only checks, then a targeted and reversible change, then, with approval, anything broader.

- Fix the spec that is wrong (security context, requests and limits, probe, image tag, selector, mount) rather than loosening the platform around it. When Pod Security rejects pods, the message lists the fields to set; for the restricted level these are `allowPrivilegeEscalation: false`, `capabilities.drop: ["ALL"]`, `runAsNonRoot: true` and `seccompProfile.type: RuntimeDefault` (or `Localhost`) in the pod or container `securityContext`. Check the image can run that way. Lowering the namespace's level, or moving the workload to an unenforced namespace, removes the protection for every workload there.
- Prefer the controller to manual deletion: a corrected manifest or a rollback to the previous revision goes through the rollout's surge and availability rules; deleting pods or ReplicaSets by hand does not.
- For a trust error, add the right CA to the trust bundle from its authoritative source, checked by fingerprint (never a certificate copied from the server's own handshake), keep the old CA while others still need it, and roll the pods. Turning off verification or switching to plain HTTP sends data to whoever answers.
- Scale up from zero in steps, once the reason for the stop is known and dealt with, watching the signal that caused it. A HorizontalPodAutoscaler resets a manual replica count at its next sync, except zero, which pauses it until the count is raised; change its bounds instead.
- Volumes: with `allowVolumeExpansion: true`, a CSI driver that supports online expansion grows the volume while it is in use. If the PVC shows the new capacity, its events end with `FileSystemResizeSuccessful`, nothing in its conditions or status says a resize is still pending, and `df` in the pod shows the new size, the resize is finished and no restart is needed. A PVC cannot shrink.
- CronJobs: `concurrencyPolicy: Allow` (the default) lets runs pile up when a run outlasts the schedule; `Forbid` skips a run while one is active; `Replace` replaces it. `suspend: true` stops new runs but leaves running Jobs alone. A Job without the CronJob in its `ownerReferences` is separate work.
- Resources: an OOM kill is fixed by the right memory limit or by the leak, not by removing limits; CPU throttling is a limit, not a crash.

## Actions that lose data or availability

Propose these only with the impact stated, explicit approval from the workload's owner or the incident lead, and the safer alternative alongside:

- `kubectl delete` on a PersistentVolumeClaim, a namespace or a StatefulSet, or with `--all` or a broad label selector. List exactly what matches with `kubectl get` first. Deleting what a controller or schedule recreates (pods of a ReplicaSet, Jobs of an unsuspended CronJob) does not stop the problem; stop or fix the source first. A claim whose volume has reclaim policy `Delete` takes the disk with it. Deleting a Job kills its pods and their work.
- Restarting or deleting the only replica, or the pod of a single-replica StatefulSet, is an outage for that service. `kubectl rollout restart` replaces every pod. Force deletion (`--force --grace-period=0`) of a StatefulSet pod can leave two copies writing the same storage.
- `kubectl drain` evicts every pod on a node: check PodDisruptionBudgets and single-replica workloads first. `kubectl cordon` alone only stops new pods and is easy to undo.
- Removing finalizers, scaling to zero, editing a live object outside its GitOps source, or changing a namespace's security level.

## Read-only commands

```
kubectl get pods -n <ns> -o wide
kubectl describe pod <pod> -n <ns>
kubectl get events -n <ns> --sort-by=.lastTimestamp
kubectl logs <pod> -n <ns> -c <container> --previous --tail=100
kubectl get deploy <name> -n <ns> -o yaml --show-managed-fields
kubectl rollout history deploy/<name> -n <ns>
kubectl get pvc,pv -n <ns>
kubectl describe node <node>
kubectl top pods -n <ns>
```

With tools, run these first. Every change (apply, patch, scale, rollout, delete, drain, cordon, an exec that writes) is a proposal for a person to approve before it runs.
