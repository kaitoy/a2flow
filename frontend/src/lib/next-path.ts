/** @module next-path — The page a sign-in returns to, carried as `/login?next=`. */

/**
 * Return `value` if it is a path on this site, else `/`. The value comes from
 * the URL, so only a path that stays on the current origin passes: one leading
 * `/`, no backslash and no control character, which rules out `//evil.example`
 * and `/\evil.example` (both read by browsers as another host). The backend
 * applies the same rule to the `next` it is handed for SSO.
 */
export function safeNextPath(value: string | null | undefined): string {
  if (
    !value?.startsWith("/") ||
    value.startsWith("//") ||
    value.includes("\\") ||
    // biome-ignore lint/suspicious/noControlCharactersInRegex: rejecting them is the point
    /[\u0000-\u001f\u007f]/.test(value)
  ) {
    return "/";
  }
  return value;
}

/**
 * Return the sign-in page's path, asking it to return to `next` afterwards.
 * Plain `/login` when `next` is the welcome page or not a path on this site.
 */
export function loginPath(next: string): string {
  const safe = safeNextPath(next);
  return safe === "/" ? "/login" : `/login?next=${encodeURIComponent(safe)}`;
}
