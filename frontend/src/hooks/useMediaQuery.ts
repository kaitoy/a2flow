"use client";

import { useEffect, useState } from "react";

/**
 * Track whether a CSS media query currently matches, re-rendering when it
 * changes. Returns `false` on the server and during the first client render
 * (before the effect runs), so SSR markup stays deterministic.
 *
 * @param query - A media query string, e.g. `"(pointer: coarse)"`.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);

  useEffect(() => {
    const mql = window.matchMedia(query);
    setMatches(mql.matches);
    const onChange = (e: MediaQueryListEvent) => setMatches(e.matches);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}
