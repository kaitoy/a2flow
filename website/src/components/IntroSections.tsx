import type {ReactNode} from 'react';

import '@site/src/css/intro.css';

/**
 * The presentational pieces of the manual's Introduction page.
 *
 * The page exists in two locales, so the markup lives here and each locale's
 * `intro.mdx` supplies only its own prose as children. Nothing here carries
 * text of its own — the decorative SVGs are label-free on purpose, since a
 * diagram with baked-in English would break in the `ja` build.
 *
 * Styles come from `intro.css`, scoped under `.a2f-intro` the way the landing
 * page scopes its own under `.a2flow-home`.
 */

/** Props shared by the wrappers that only group their children. */
interface WrapperProps {
  children: ReactNode;
}

/**
 * The page root. Establishes the `.a2f-intro` scope every style keys off and
 * the stacking context the hero's glow sits behind.
 */
export function IntroPage({children}: WrapperProps): ReactNode {
  return <div className="a2f-intro">{children}</div>;
}

/** Props for {@link IntroHero}. */
interface IntroHeroProps {
  /** Small uppercase kicker above the headline. */
  eyebrow: ReactNode;
  /** The page's `h1`. Wrap a fragment of it in `<span className="grad">` to
   * pick up the accent-to-secondary gradient. */
  title: ReactNode;
  /** The lead paragraph. */
  children: ReactNode;
}

/**
 * The opening statement: kicker, headline, and lead paragraph over a soft
 * radial glow. Renders the page's only `h1`, which is why the MDX sets
 * `hide_title: true`.
 */
export function IntroHero({eyebrow, title, children}: IntroHeroProps): ReactNode {
  return (
    <header className="intro-hero">
      <span className="intro-glow" aria-hidden="true" />
      <span className="intro-eyebrow">{eyebrow}</span>
      <h1 className="intro-title">{title}</h1>
      <div className="intro-lead">{children}</div>
    </header>
  );
}

/** Side-by-side frame for the two {@link IntroPanel}s. */
export function IntroContrast({children}: WrapperProps): ReactNode {
  return <div className="intro-contrast">{children}</div>;
}

/** Props for {@link IntroPanel}. */
interface IntroPanelProps {
  /** `past` renders the faded "how it used to be" panel, `next` the lit one. */
  kind: 'past' | 'next';
  /** The panel's heading. */
  title: ReactNode;
  /** The panel's prose. */
  children: ReactNode;
}

/**
 * One half of the contrast: an agent sitting inside a workflow, versus an
 * agent that is the workflow. The `past` panel is deliberately quieter.
 */
export function IntroPanel({kind, title, children}: IntroPanelProps): ReactNode {
  return (
    <section className={`intro-panel intro-panel-${kind}`}>
      {kind === 'past' ? <PastMark /> : <NextMark />}
      <h2 className="intro-panel-title">{title}</h2>
      <div className="intro-panel-body">{children}</div>
    </section>
  );
}

/** A process drawn as boxes, with one of them labelled "AI". Decorative. */
function PastMark(): ReactNode {
  return (
    <svg className="intro-mark" viewBox="0 0 104 32" fill="none" aria-hidden="true">
      <path className="mark-wire" d="M27 16h9M63 16h9" strokeWidth="1.6" strokeLinecap="round" />
      <rect className="mark-box" x="2" y="6" width="25" height="20" rx="6" strokeWidth="1.6" />
      <rect className="mark-box mark-box-ai" x="38" y="4" width="25" height="24" rx="6" strokeWidth="1.6" />
      <path className="mark-spark" d="M50.5 10.5l1.1 2.6 2.6 1.1-2.6 1.1-1.1 2.6-1.1-2.6-2.6-1.1 2.6-1.1z" />
      <rect className="mark-box" x="74" y="6" width="25" height="20" rx="6" strokeWidth="1.6" />
    </svg>
  );
}

/** One shape holding the whole process. Decorative. */
function NextMark(): ReactNode {
  return (
    <svg className="intro-mark" viewBox="0 0 104 32" fill="none" aria-hidden="true">
      <rect className="mark-box mark-box-whole" x="2" y="3" width="100" height="26" rx="13" strokeWidth="1.6" />
      <path className="mark-spark" d="M20 9.5l1.5 3.5 3.5 1.5-3.5 1.5L20 19.5 18.5 16 15 14.5l3.5-1.5z" />
      <circle className="mark-dot" cx="40" cy="16" r="2.6" />
      <circle className="mark-dot" cx="54" cy="16" r="2.6" />
      <circle className="mark-dot" cx="68" cy="16" r="2.6" />
      <circle className="mark-dot" cx="82" cy="16" r="2.6" />
    </svg>
  );
}

/** The three-act row. Cards stack below the `sm` width. */
export function IntroActs({children}: WrapperProps): ReactNode {
  return <div className="intro-acts">{children}</div>;
}

/** Which glyph an {@link IntroAct} card leads with. */
type ActIcon = 'design' | 'run' | 'control';

/** Props for {@link IntroAct}. */
interface IntroActProps {
  /** The act's number, e.g. `01`. */
  step: ReactNode;
  /** Which decorative glyph to show. */
  icon: ActIcon;
  /** The act's heading. */
  title: ReactNode;
  /** The act's prose. */
  children: ReactNode;
}

/** Label-free glyphs, keyed by act. */
const ACT_ICONS: Record<ActIcon, ReactNode> = {
  design: (
    <>
      <path d="M21 14a2 2 0 0 1-2 2H8l-4 4V5a2 2 0 0 1 2-2h13a2 2 0 0 1 2 2z" />
      <path d="M12.5 6.5l1 2.4 2.4 1-2.4 1-1 2.4-1-2.4-2.4-1 2.4-1z" />
    </>
  ),
  run: (
    <>
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
    </>
  ),
  control: (
    <>
      <circle cx="12" cy="8" r="6" />
      <path d="m9.5 10.5 1.7 1.7 3.4-3.4" />
      <path d="M15.5 13.2 17 22l-5-3-5 3 1.5-8.8" />
    </>
  ),
};

/**
 * One act of the story — design, run, control — as a glass card carrying a
 * step number, a glyph, a heading, and its prose.
 */
export function IntroAct({step, icon, title, children}: IntroActProps): ReactNode {
  return (
    <section className="intro-act">
      <span className="intro-act-head">
        <svg
          className="intro-act-icon"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true">
          {ACT_ICONS[icon]}
        </svg>
        <span className="intro-act-step">{step}</span>
      </span>
      <h2 className="intro-act-title">{title}</h2>
      <div className="intro-act-body">{children}</div>
    </section>
  );
}

/** Props for {@link IntroClosing}. */
interface IntroClosingProps {
  /** The large gradient line. */
  headline: ReactNode;
  /** The sentence under it. */
  children: ReactNode;
}

/** The closing beat: three words and the sentence that lands them. */
export function IntroClosing({headline, children}: IntroClosingProps): ReactNode {
  return (
    <section className="intro-closing">
      <p className="intro-closing-headline">{headline}</p>
      <div className="intro-closing-body">{children}</div>
    </section>
  );
}

/** Props for {@link IntroNext}. */
interface IntroNextProps {
  /** The section's heading. */
  title: ReactNode;
  /** A Markdown list; each item renders as a card. */
  children: ReactNode;
}

/**
 * The "where to go next" grid. Children stay a plain Markdown list so the
 * links keep their `.md` targets and Docusaurus can still resolve them per
 * locale; the styling turns each item into a card.
 */
export function IntroNext({title, children}: IntroNextProps): ReactNode {
  return (
    <section className="intro-next">
      <h2 className="intro-next-title">{title}</h2>
      {children}
    </section>
  );
}
