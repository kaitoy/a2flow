import type * as Preset from '@docusaurus/preset-classic';
import type {Config} from '@docusaurus/types';
import {themes as prismThemes} from 'prism-react-renderer';

// This runs in Node.js - Don't use client-side code here (browser APIs, JSX...)

const config: Config = {
  title: 'A2Flow',
  tagline: 'Agent as Workflow',
  favicon: 'img/logo.png',

  future: {
    v4: true, // Improve compatibility with the upcoming Docusaurus v4
  },

  // Published by .github/workflows/pages.yml to GitHub Pages, which serves the
  // repository under /<projectName>/ rather than at the domain root.
  url: 'https://kaitoy.github.io',
  baseUrl: '/a2flow/',
  organizationName: 'kaitoy',
  projectName: 'a2flow',
  trailingSlash: false,

  onBrokenLinks: 'throw',
  // 'warn' rather than 'throw': Docusaurus collects anchors from Markdown
  // headings only, so the landing page's section ids (#concept, #how, …) are
  // invisible to the checker and every navbar link to them reads as broken.
  onBrokenAnchors: 'warn',

  markdown: {
    // 'detect' keeps .md files on CommonMark (only .mdx is compiled as MDX), so
    // the braces and angle brackets that run through the manual's prose stay
    // literal instead of being read as JSX.
    format: 'detect',
    // Renders ```mermaid fences through @docusaurus/theme-mermaid. The remark
    // plugin rewrites the code node itself, so this works in the CommonMark
    // .md pages above as well as in .mdx.
    mermaid: true,
    hooks: {
      onBrokenMarkdownLinks: 'throw',
    },
  },

  i18n: {
    defaultLocale: 'en',
    locales: ['en', 'ja'],
    localeConfigs: {
      en: {label: 'English'},
      ja: {label: '日本語'},
    },
  },

  // Inter (body) and Space Grotesk (display) are the application's own faces.
  headTags: [
    {
      tagName: 'link',
      attributes: {rel: 'preconnect', href: 'https://fonts.googleapis.com'},
    },
    {
      tagName: 'link',
      attributes: {rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: 'anonymous'},
    },
  ],

  stylesheets: [
    'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap',
  ],

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          editUrl: 'https://github.com/kaitoy/a2flow/tree/master/website/',
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  themes: [
    '@docusaurus/theme-mermaid',
    [
      '@easyops-cn/docusaurus-search-local',
      {
        hashed: true,
        indexBlog: false,
        docsRouteBasePath: '/docs',
        language: ['en', 'ja'],
        highlightSearchTermsOnTargetPage: true,
      },
    ],
  ],

  themeConfig: {
    image: 'img/logo.png',
    metadata: [
      {
        name: 'description',
        content:
          'A2Flow rebuilds ITSM-style, multi-person, approval-gated workflows around an AI agent.',
      },
    ],
    colorMode: {
      respectPrefersColorScheme: true,
    },
    // Both themes are named explicitly: the site follows the OS colour scheme,
    // so a diagram drawn for one of them alone is unreadable in the other.
    mermaid: {
      theme: {light: 'neutral', dark: 'dark'},
      // Mermaid's 200px default wraps a node label mid-word, which Japanese
      // hits constantly (no spaces to break on). Widening it leaves the
      // authored <br/> as the only line break in either locale.
      options: {flowchart: {wrappingWidth: 340}},
    },
    navbar: {
      title: 'A2Flow',
      logo: {
        alt: 'A2Flow',
        src: 'img/logo.png',
      },
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'manualSidebar',
          position: 'left',
          label: 'Docs',
        },
        {type: 'localeDropdown', position: 'right'},
        {
          href: 'https://github.com/kaitoy/a2flow',
          label: 'GitHub',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Manual',
          items: [
            {label: 'Introduction', to: '/docs/intro'},
            {label: 'Quick start', to: '/docs/getting-started/quick-start'},
            {label: 'Deployment', to: '/docs/operations/deployment'},
          ],
        },
        {
          title: 'Project',
          items: [
            {label: 'GitHub', href: 'https://github.com/kaitoy/a2flow'},
            {label: 'Issues', href: 'https://github.com/kaitoy/a2flow/issues'},
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} A2Flow. Built with Docusaurus.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['bash', 'json', 'yaml', 'python', 'sql', 'ini'],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
