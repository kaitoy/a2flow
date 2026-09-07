---
name: gcp-log-error-analysis
description: Fetch a Google Cloud project's Cloud Logging entries, single out the errors, and report the likely root cause, gated by a manager's explicit approval of the query scope before any logs are read. Use this skill whenever the user wants to investigate errors in Google Cloud logs — including "why is my Cloud Run service throwing 500s", "check the logs for errors in the last hour", "what's failing in project acme-prod", "do a root cause analysis from Cloud Logging", or "look at the GKE workload's error logs and tell me what broke". Also use it when the user reports a production incident on Google Cloud and the implied next step is to pull the logs and diagnose it, even if they don't say "Cloud Logging" explicitly. This skill agrees the exact scope — project, resource, time window, and severity — with the user, gets a manager's approval of that scope, reads only the matching entries, then analyzes them — it never queries logs before an approval has come back approved.
---

# GCP Log Error Analysis

Investigate errors in a Google Cloud project's logs. The core principle: reading production logs can expose sensitive data, and the query scope decides exactly what is read and how much, so you **agree the exact scope with the user, get a manager's explicit approval of that scope, read only what was approved, then analyze it and report the root cause**. Never query logs before an approval has come back approved.

## Workflow

### 1. Agree the query scope

Ask the user for whatever isn't already given. At minimum, you need:

- **Project** — the Google Cloud project whose logs to read.
- **Resource or service** — a specific Cloud Run service, GKE workload, Cloud Function, or similar; or "everything in the project" if that is what they want.
- **Time window** — an explicit start and end, or a relative range you restate as one (e.g. "the last hour" becomes the concrete start and end you will use).
- **Severity floor** — default to `ERROR` and above. Widen it only if the user asks.
- **Extra filters** — any request id, revision, region, or label the user wants the search narrowed to.

Do not guess the project, and do not widen the time window on your own — a broader scope reads more data than the user asked for. For a genuinely low-stakes field (the severity floor defaulting to `ERROR`) you may propose the default, but say what you're defaulting to and let the user override it.

Once you have everything, summarize the finalized scope back to the user before moving on. This exact summary is also what the approver decides on in the next step.

### 2. Get manager approval

This step is mandatory. Before any logs are read, a manager must explicitly approve the scope from step 1 — not the idea of a log search, that exact scope.

Address the request to a **team** of managers rather than to one named person whenever you can, so the investigation is not blocked on one person's availability. Name a single person only when the decision genuinely belongs to them.

The request needs a short title naming the project (e.g. "Analyze Cloud Logging errors: `<project>`") and a body carrying the finalized scope verbatim, so the approver decides on exactly what will be read. Tell the user in plain text that the request has gone out and who it went to.

Then wait for the decision. If it comes back approved, continue to step 3. If it comes back rejected, stop — read nothing — and tell the user the manager declined, including any comment they left. If there is nobody who can approve, stop as well and say so: reading the logs without an approval is not an option.

### 3. Fetch the matching log entries

Read exactly the scope that was approved. Nothing may widen between the approval and the query; if the scope has to change, go back to step 2 and have the new scope approved.

However you reach the logs may name its parameters differently from the terms used here, so map the approved scope onto what it accepts — the project onto a project or resource-name field, the time window onto timestamp bounds, the severity floor onto a severity filter, and any extra filters onto its query language.

If the query returns an error (permission denied, an invalid filter, a quota limit, etc.), report the exact error to the user and stop — do not retry with a broadened scope or guess a fix. If it returns nothing, say so plainly: within this scope there are no matching entries.

### 4. Single out the errors and analyze

From what came back, separate the `ERROR`-and-above entries from the ordinary noise. Group them by message signature, service, and revision so repeated instances of one failure collapse into a single group.

For the dominant group, work out:

- **When** — the first and last occurrence in the window, and whether the rate is steady, spiking, or a one-off.
- **How much** — the count, and how it compares to the other groups.
- **What changed** — whether onset lines up with a deploy, a revision rollout, a traffic change, or an upstream dependency.
- **The signature** — the shortest stack frame or error string that identifies the failure.
- **The likely cause** — and whether you can see it directly in the log entries or are inferring it from the pattern.

### 5. Report the findings

Show the user the error groups, the leading group's likely root cause, and the evidence that supports it. Then say what you would check or change next — do not act on it from this skill; this skill reads and explains, it does not remediate.

## Reporting format

Close with a short, factual summary:

```
Analyzed Cloud Logging errors for <project>.
  Manager approval: approved by <approver>
  Scope: <resource>, <time window>, severity >= <floor>
  Error groups: <n>  (top: "<signature>" x<count>)
  Likely root cause: <one line>
  Evidence: <observed in the logs | inferred from the pattern>
```

If the manager rejected the request, the query failed, or there were no matching entries in scope, replace the success summary with what happened at that step and state clearly that no root cause was determined.
