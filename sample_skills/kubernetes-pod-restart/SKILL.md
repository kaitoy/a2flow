---
name: kubernetes-pod-restart
description: Restart Kubernetes pods safely using kubectl. Use this skill whenever the user wants to restart, recycle, bounce, or cycle pods, deployments, statefulsets, or daemonsets — including requests phrased as "restart the api pods", "my pod is stuck in CrashLoopBackOff, restart it", "roll the deployment", "kill that pod so it comes back fresh", or "pods need a restart after the config change". Also use it when the user describes a symptom (a hung, crashing, OOMKilled, or stale pod) and the implied fix is a restart, even if they don't say the word "restart".
---

# Kubernetes Pod Restart

Restart Kubernetes workloads safely. The core principle: a restart in the wrong namespace can take down production, so you **identify the exact target, show it to the user, get confirmation, then act, then verify**. Never skip the confirmation step.

## Two restart methods

There is no `kubectl restart pod` command. Choose the right approach:

**`kubectl rollout restart`** — the default and preferred method. Works on Deployments, StatefulSets, and DaemonSets. It does a rolling restart: new pods come up before old ones terminate, so there is no downtime. Use this whenever the user refers to a workload, a service, or "the pods" of an app in general.

**`kubectl delete pod <name>`** — deletes a single pod; its controller (ReplicaSet/Deployment/etc.) recreates it. Use this only when the user genuinely wants one specific pod gone — e.g. a single stuck pod among many healthy replicas. The replacement pod is created fresh, but for a brief moment that replica is down. A bare pod with no controller will NOT come back — warn the user if you detect this.

When in doubt, prefer `rollout restart` on the owning workload. It is the safe, standard answer.

## Workflow

### 1. Identify the target

The user specifies the target one of two ways:

**By name** — they name the resource and (ideally) the namespace: "restart the `api` deployment in `prod`". If the namespace is missing, ask for it rather than guessing — defaulting to `default` is a common cause of "nothing happened" or, worse, hitting the wrong environment. Confirm the resource exists:

```
kubectl get deployment <name> -n <namespace>
```

**By symptom** — they describe a problem: "restart whatever is CrashLoopBackOff-ing", "the OOMKilled pod". Investigate first:

```
kubectl get pods -n <namespace>
kubectl get pods -A   # if namespace is unknown
```

Find the matching pod(s), then trace each one to its owning workload so you can do a clean `rollout restart`:

```
kubectl get pod <pod> -n <namespace> -o jsonpath='{.metadata.ownerReferences[0].kind}/{.metadata.ownerReferences[0].name}'
```

A pod owned by a ReplicaSet belongs to a Deployment — restart the Deployment, not the ReplicaSet.

### 2. Confirm before acting

This step is mandatory. Show the user exactly what you found and what you intend to run, then wait for explicit approval:

```
Target: deployment/api  (namespace: prod)
  Current pods: api-7d4f8-abc12 (Running), api-7d4f8-xyz89 (Running)
Planned command: kubectl rollout restart deployment/api -n prod

Proceed?
```

Be especially deliberate when the namespace or context looks like production (`prod`, `production`, `live`, etc.) — call it out explicitly so the user registers it. If something is ambiguous (multiple matching resources, a bare pod with no controller, an unclear namespace), surface it here and let the user decide instead of picking for them.

### 3. Execute

After approval, run the chosen command:

```
kubectl rollout restart deployment/<name> -n <namespace>
```

or, for a single pod:

```
kubectl delete pod <pod> -n <namespace>
```

### 4. Verify the restart completed

Don't stop at "command ran". A restart that leaves pods crashing is not a successful restart. Watch it land:

```
kubectl rollout status deployment/<name> -n <namespace> --timeout=120s
```

For a deleted pod, confirm the replacement is Ready:

```
kubectl get pods -n <namespace> -w   # or poll kubectl get pods until Ready
```

Then report the outcome: which pods are now running, that they reached Ready, and how long it took. If `rollout status` times out or pods are crashing, say so clearly and show the relevant `kubectl describe` / `kubectl logs` output so the user can debug — a failed rollout is important news, not something to gloss over.

## Reporting format

Close with a short, factual summary:

```
Restarted deployment/api in prod.
  Old pods terminated: api-7d4f8-abc12, api-7d4f8-xyz89
  New pods Ready:      api-9a1c2-def34, api-9a1c2-ghi56
  Rollout completed in 18s.
```

If it failed, replace the success lines with what went wrong and the next diagnostic step.
