/**
 * Inline script run `beforeInteractive` to set `document.documentElement.dataset.theme`
 * from `localStorage['a2flow.theme']` (or the OS preference) before hydration,
 * avoiding a light/dark flash. Shared by the root layout and `global-error.tsx`,
 * which renders its own `<html>`/`<body>` and so needs the same script again.
 */
export const NO_FLASH_THEME_SCRIPT = `(() => {
  try {
    const stored = localStorage.getItem('a2flow.theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const theme = stored === 'light' || stored === 'dark' ? stored : prefersDark ? 'dark' : 'light';
    document.documentElement.dataset.theme = theme;
  } catch (_) {
    document.documentElement.dataset.theme = 'light';
  }
})();`;
