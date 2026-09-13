---
name: gke-pod-restart
description: Restart a specific Kubernetes Pod running on a Google Kubernetes Engine (GKE) cluster through the registered GKE MCP server, gated by a manager's explicit approval of exactly which pod before it is touched. Use this skill whenever the user wants to restart, recycle, bounce, or cycle a single named pod on a GKE cluster through the connected MCP tooling — including requests phrased as "restart the api-7d4f8-abc12 pod on the prod cluster", "that pod on GKE is stuck, restart it through the MCP server", or "cycle the crashing pod in the billing cluster". This skill agrees the exact target — project, cluster, location, namespace, and pod name — with the user, gets a manager's explicit approval of that exact target, deletes only the approved pod through the GKE MCP server so its owning controller recreates it, then reports the outcome — it never deletes a pod before an approval has come back approved.
---

# GKE Pod Restart

Restart a single Kubernetes Pod on a Google Kubernetes Engine cluster through the registered **GKE MCP Server**. The core principle: deleting the wrong pod can take down a workload, and a Pod with no owning controller will not come back at all, so you **agree the exact target with the user, get a manager's explicit approval of that exact target, delete only what was approved, then confirm the outcome**. Never delete a pod before an approval has come back approved.

## Workflow

### 1. Agree the target

Ask the user for whatever isn't already given. At minimum, you need:

- **Project** — the Google Cloud project the cluster belongs to.
- **Cluster** — the GKE cluster name and its location (zone or region).
- **Namespace** — the Kubernetes namespace the pod lives in.
- **Pod name** — the exact pod to restart, not a workload name or a label selector.

Do not guess the namespace or pod name — restarting the wrong pod can disrupt a workload that was never meant to be touched. Before finalizing the target, look the pod up (e.g. `get_k8s_resource`) and check its `ownerReferences`: a pod owned by a ReplicaSet/Deployment/StatefulSet/DaemonSet comes back on its own once deleted, but a bare pod with no controller does not. If the pod has no controller, say so plainly and let the user decide whether to proceed anyway.

Once you have everything, summarize the finalized target back to the user before moving on. This exact summary is also what the approver decides on in the next step.

### 2. Get manager approval

This step is mandatory. Before the pod is touched, a manager must explicitly approve the exact target from step 1 — not the idea of a restart, that exact pod.

Address the request to a **team** of managers rather than to one named person whenever you can, so the restart is not blocked on one person's availability. Name a single person only when the decision genuinely belongs to them.

The request needs a short title naming the pod (e.g. "Restart GKE pod: `<pod>` (`<cluster>`/`<namespace>`)") and a body carrying the finalized target verbatim, so the approver decides on exactly what will be deleted. Tell the user in plain text that the request has gone out and who it went to.

Then wait for the decision. If it comes back approved, continue to step 3. If it comes back rejected, stop — delete nothing — and tell the user the manager declined, including any comment they left. If there is nobody who can approve, stop as well and say so: deleting the pod without an approval is not an option.

### 3. Delete the approved pod

Delete exactly the pod that was approved. Nothing may change between the approval and the deletion; if the target has to change, go back to step 2 and have the new target approved.

Run the deletion through the **GKE MCP Server**'s `delete_k8s_resource` tool, addressing it at the approved project, cluster, location, namespace, and pod name. There is no dedicated "restart" operation — deleting the pod is what causes its owning controller to recreate it.

If the deletion returns an error (permission denied, the pod no longer exists, an invalid target, etc.), report the exact error to the user and stop — do not retry against a different pod or guess a fix.

### 4. Confirm the restart completed

Don't stop at "the delete call succeeded". Check that a replacement pod came up (e.g. `list_k8s_events` or `get_k8s_resource` on the workload) and report what you find. For a pod with no owning controller, there is no replacement to wait for — say so, matching what you flagged in step 1.

## Reporting format

Close with a short, factual summary:

```
Restarted pod <pod> (<cluster>/<namespace>).
  Manager approval: approved by <approver>
  Deleted: <pod>
  Replacement: <new-pod-name> (Ready) | none (bare pod, as flagged)
```

If the manager rejected the request, the deletion failed, or no replacement pod ever came up, replace the success summary with what happened at that step and state clearly that the restart is not confirmed complete.
