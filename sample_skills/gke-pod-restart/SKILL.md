---
name: gke-pod-restart
description: Restart the Pods of a Deployment or StatefulSet -- or, when the user wants exactly one Pod gone, a single named Pod -- on a Google Kubernetes Engine (GKE) cluster through the registered GKE MCP server, gated by a manager's explicit approval of the exact target before anything is touched. Use this skill whenever the user wants to restart, recycle, bounce, roll, or cycle pods, a Deployment, or a StatefulSet on a GKE cluster through the connected MCP tooling -- including requests phrased as "roll the api Deployment on the prod cluster", "restart the billing StatefulSet", "that pod on GKE is stuck, restart it through the MCP server", or "cycle the crashing pod in the billing cluster". This skill agrees the exact target -- project, cluster, location, namespace, and either a workload name or a single pod name -- with the user, gets a manager's explicit approval of that exact target, performs a rolling restart of the workload (or deletes only the approved pod) through the GKE MCP server, then reports the outcome -- it never touches anything before an approval has come back approved.
---

# GKE Pod Restart

Restart Kubernetes workloads on a Google Kubernetes Engine cluster through the registered **GKE MCP Server**. The core principle: restarting the wrong workload -- or deleting the wrong pod -- can take down production, and a Pod with no owning controller will not come back at all, so you **agree the exact target with the user, get a manager's explicit approval of that exact target, act on only what was approved, then confirm the outcome**. Never touch anything before an approval has come back approved.

## Two restart methods

There is no dedicated "restart" operation on either the workload or a pod. Choose the right approach:

**A rolling restart of the workload** (Deployment or StatefulSet) -- the default and preferred method. Patching the workload's pod template causes its controller to replace every pod with a fresh one, one at a time, so there is no downtime. Use this whenever the user refers to a workload, a service, or "the pods" of an app in general.

**Deleting a single pod** -- its owning controller recreates it. Use this only when the user genuinely wants one specific pod gone, e.g. a single stuck pod among many healthy replicas. A bare pod with no controller will NOT come back -- warn the user if you detect this.

When in doubt, prefer a rolling restart of the owning workload. It is the safe, standard answer.

## Workflow

### 1. Agree the target

Ask the user for whatever isn't already given. At minimum, you need:

- **Project** -- the Google Cloud project the cluster belongs to.
- **Cluster** -- the GKE cluster name and its location (zone or region).
- **Namespace** -- the Kubernetes namespace the target lives in.
- **Either**:
  - **Workload** -- the exact Deployment or StatefulSet name, for a rolling restart, or
  - **Pod name** -- the exact pod to delete, not a workload name or a label selector, when the user wants only that one pod gone.

Do not guess the namespace, workload name, or pod name -- restarting the wrong workload or deleting the wrong pod can disrupt something that was never meant to be touched. Before finalizing the target, look it up (e.g. `get_k8s_resource`): for a workload, confirm its kind is exactly Deployment or StatefulSet; for a pod, check its `ownerReferences` -- a pod owned by a ReplicaSet/Deployment/StatefulSet comes back on its own once deleted, but a bare pod with no controller does not. If the pod has no controller, say so plainly and let the user decide whether to proceed anyway.

Once you have everything, summarize the finalized target back to the user before moving on. This exact summary is also what the approver decides on in the next step.

### 2. Get manager approval

This step is mandatory. Before anything is touched, a manager must explicitly approve the exact target from step 1 -- not the idea of a restart, that exact workload or pod.

Address the request to a **team** of managers rather than to one named person whenever you can, so the restart is not blocked on one person's availability. Name a single person only when the decision genuinely belongs to them.

The request needs a short title naming the target (e.g. "Restart GKE workload: `<kind>/<name>` (`<cluster>`/`<namespace>`)" or "Restart GKE pod: `<pod>` (`<cluster>`/`<namespace>`)") and a body carrying the finalized target verbatim, so the approver decides on exactly what will be touched. Tell the user in plain text that the request has gone out and who it went to.

Then wait for the decision. If it comes back approved, continue to step 3. If it comes back rejected, stop -- touch nothing -- and tell the user the manager declined, including any comment they left. If there is nobody who can approve, stop as well and say so: acting without an approval is not an option.

### 3. Restart the approved target

Act on exactly what was approved. Nothing may change between the approval and the action; if the target has to change, go back to step 2 and have the new target approved.

**Rolling restart of a Deployment or StatefulSet**: run it through the **GKE MCP Server**'s `patch_k8s_resource` tool, addressing it at the approved project, cluster, location, namespace, kind, and workload name, and adding or bumping a restart timestamp annotation on its pod template (`spec.template.metadata.annotations`). The workload's own controller then replaces its pods for you -- there is nothing further to trigger.

**Deleting a single pod**: run it through the GKE MCP Server's `delete_k8s_resource` tool, addressing it at the approved project, cluster, location, namespace, and pod name.

If the call returns an error (permission denied, the target no longer exists, an invalid target, etc.), report the exact error to the user and stop -- do not retry against a different target or guess a fix.

### 4. Confirm the restart completed

Don't stop at "the call succeeded". For a workload, poll it (e.g. `get_k8s_resource`) until its updated replicas match its desired replica count, or check `list_k8s_events` for the rollout's progress, and report what you find. For a deleted pod, check that a replacement pod came up (e.g. `list_k8s_events` or `get_k8s_resource` on the workload). For a pod with no owning controller, there is no replacement to wait for -- say so, matching what you flagged in step 1.

## Reporting format

Close with a short, factual summary. For a workload:

```
Rolling-restarted deployment/api (my-cluster/prod).
  Manager approval: approved by <approver>
  Pods replaced: 3/3
```

For a single pod:

```
Restarted pod <pod> (<cluster>/<namespace>).
  Manager approval: approved by <approver>
  Deleted: <pod>
  Replacement: <new-pod-name> (Ready) | none (bare pod, as flagged)
```

If the manager rejected the request, the action failed, or the rollout/replacement never completed, replace the success summary with what happened at that step and state clearly that the restart is not confirmed complete.
