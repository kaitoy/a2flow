"use client";

import { animated, useTransition } from "@react-spring/web";
import { useEffect, useState } from "react";
import { useMotionConfig } from "@/lib/motion";
import { useTheme } from "./ThemeProvider";
import { Tooltip } from "./ui/tooltip";

interface ThemeToggleProps {
  className?: string;
}

/** Icon button that toggles between light and dark themes. */
export function ThemeToggle({ className }: ThemeToggleProps) {
  const { theme, toggleTheme } = useTheme();
  // Defer theme-dependent rendering until after hydration to avoid SSR mismatch.
  // The server always renders as "light"; the client corrects itself after mount.
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);
  const isDark = mounted && theme === "dark";
  const config = useMotionConfig("snappy");
  const iconTransitions = useTransition(isDark, {
    from: { opacity: 0, rotate: -90 },
    enter: { opacity: 1, rotate: 0 },
    leave: { opacity: 0, rotate: 90 },
    config,
  });
  const cls = [
    "inline-flex h-9 w-9 pointer-coarse:h-11 pointer-coarse:w-11 cursor-pointer items-center justify-center rounded-full relative overflow-hidden",
    "glass-panel text-on-surface",
    "transition-[transform,translate,scale,box-shadow,color,background-color] duration-[var(--motion-duration-base)] ease-[var(--motion-ease-standard)]",
    "hover:shadow-glow hover:text-accent motion-safe:hover:scale-105 motion-safe:active:scale-95",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  const label = isDark ? "Switch to light theme" : "Switch to dark theme";
  return (
    <Tooltip label={label} placement="bottom">
      <button type="button" onClick={toggleTheme} className={cls} aria-label={label}>
        {iconTransitions((style, dark) => (
          <animated.span
            style={{
              opacity: style.opacity,
              transform: style.rotate.to((r) => `rotate(${r}deg)`),
            }}
            className="absolute inset-0 flex items-center justify-center"
            aria-hidden="true"
          >
            {dark ? <SunIcon /> : <MoonIcon />}
          </animated.span>
        ))}
      </button>
    </Tooltip>
  );
}

function SunIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="4" />
      <path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
    </svg>
  );
}
