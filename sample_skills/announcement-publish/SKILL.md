---
name: announcement-publish
description: Draft an announcement and publish it after human approval. Use this skill whenever the user wants to write and put out a notice, announcement, or heads-up — including requests phrased as "draft an announcement and publish it", "write a release note and post it", "compose a heads-up about the maintenance window", "let everyone know we shipped the new feature", or "post a public notice for the outage". Also use it when the user describes a message they want communicated to others (a release, an outage, a policy change, an event) and the implied action is to write it up and publish it, even if they don't say the word "announce". This skill produces text only — it never runs external commands or external tools; "publishing" means presenting the finalized text.
---

# Announcement Publish

Draft an announcement, get it approved by a human, then publish it. The core principle: an announcement goes out to other people, so a wrong or premature one is hard to take back. You **draft it, get explicit approval of the wording, finalize the format, get explicit approval to publish, then publish, then confirm**. Never publish without both approvals.

This skill is self-contained: every step is something you do by writing text. Do not run shell commands or call any external tool. "Publishing" here means presenting the finalized announcement as your final output — nothing leaves this conversation.

## Workflow

### 1. Draft

From the user's request, write a first draft of the announcement. Capture the audience, the key message, any dates or impact, and a call to action if relevant. Keep it short and plain at this stage — wording gets polished later. Show the draft to the user.

### 2. Get approval of the draft

This step is mandatory. Before going any further, get the user's explicit approval of the draft wording. Show them exactly what you intend to send and wait for their go-ahead.

If they approve, continue to finalizing. If they reject it, do not publish anything — revise per their feedback or stop, and say clearly that the draft was not approved.

### 3. Finalize the format

Take the approved draft and format it cleanly: a subject or headline, the body, and a closing line (and a clear date or impact line if applicable). Do not change the meaning the user approved — only tidy the structure and wording. Show the finalized version.

### 4. Get approval to publish

This step is also mandatory, and it is separate from the draft approval. This is the final go/no-go: show the user the finalized announcement and get their explicit approval to publish it.

If they approve, publish. If they reject it, do not publish — say clearly that publishing was declined and stop.

### 5. Publish

Only after both approvals, present the finalized announcement as the published result. This skill does not send it anywhere, so "published" means showing the final text clearly as your output.

## Reporting format

Close with a short, factual summary:

```
Published announcement.
  Draft approved ✓, publish approved ✓

--- Announcement ---
Subject: <headline>

<final body>

<closing line>
--------------------
```

If approval was declined at either step, replace the success summary with which step was declined and confirm that nothing was published.
