# A2Flow manual site

The A2Flow user manual, built with [Docusaurus](https://docusaurus.io/) and published to
GitHub Pages at <https://kaitoy.github.io/a2flow/> by
[`.github/workflows/pages.yml`](../.github/workflows/pages.yml).

## What belongs here

This site is for **people who use or operate A2Flow**. Developer-facing internal
references stay in the repository instead:

| Content | Lives in |
|---|---|
| A2UI rendering flow | [`docs/a2ui-flow.md`](../docs/a2ui-flow.md) |
| Design system | [`DESIGN.md`](../DESIGN.md) |
| Repository layout, toolchain, testing, git hooks, generated API types | [`README.md`](../README.md) |
| REST API reference | [`backend/README.md`](../backend/README.md) |

## Commands

```bash
pnpm install
pnpm start                 # dev server on http://localhost:3100/a2flow/ (English)
pnpm start --locale ja     # dev server in another locale: ja, es, zh-CN, ko, fr (one at a time)
pnpm build                 # builds every locale; fails on broken links
pnpm serve                 # serves the build — the only way to exercise search
python scripts/check-translations.py  # every translation still has the English page's shape
```

Every page has an English original under `docs/` and a translation under
`i18n/<locale>/docusaurus-plugin-content-docs/current/` for each of `ja`, `es`, `zh-CN`, `ko`
and `fr`. All must be updated in the same change.
