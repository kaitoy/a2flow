/** @module constants — Side-effect-free shared constants safe to import anywhere. */

/**
 * ID of the seeded system user. Every persistent record's ``createdBy`` /
 * ``updatedBy`` must reference an existing user, so until real authentication
 * exists this is the default acting identity sent in the ``X-User-Id`` header
 * (and the bootstrap actor for creating the first real user).
 */
export const SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000000";
