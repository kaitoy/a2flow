/**
 * Shared presentation helpers for {@link CertificateGrant}, used by the tool
 * certificate list and its detail page so the two describe a grant the same way.
 *
 * The stored values (`approval`, `initiator`) name the *path* a certificate was
 * issued through; the labels here name the **person** it came from, because that
 * is the question someone reading an audit trail is actually asking.
 */

import type { CertificateGrant } from "@/lib/api";

/** Human-readable label for where a certificate's authority came from. */
export const CERTIFICATE_GRANT_LABEL: Record<CertificateGrant, string> = {
  approval: "Approver",
  initiator: "Run initiator",
};

/**
 * Tailwind background-color class for the small dot beside a grant label.
 *
 * An approver's grant is accented because it is the one a human was asked to
 * weigh; an initiator's is neutral because it came with the run itself.
 */
export const CERTIFICATE_GRANT_DOT_CLASS: Record<CertificateGrant, string> = {
  approval: "bg-accent",
  initiator: "bg-on-surface-variant",
};
