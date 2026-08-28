import Translate, {translate} from '@docusaurus/Translate';
import useBaseUrl from '@docusaurus/useBaseUrl';
import Layout from '@theme/Layout';
import {type ReactNode, useEffect, useRef} from 'react';

import '@site/src/css/homepage.css';

/** How long each beat of the hero's self-playing session lasts, in ms. */
const STEP_DELAY = 2300;
/** How long the finished session stays on screen before it replays, in ms. */
const HOLD_AT_END = 5200;

/**
 * The project's landing page: what A2Flow is, how a run unfolds, and where the
 * pieces sit. Carried over from the standalone homepage that used to be served
 * at the site root, so the markup and the styles in homepage.css are the same
 * ones — only the header, the footer and the theme toggle are gone, since the
 * Docusaurus layout supplies those now.
 */
export default function Home(): ReactNode {
  const rootRef = useRef<HTMLDivElement>(null);
  const logoUrl = useBaseUrl('/img/logo.png');

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return undefined;

    // Gates the scroll-reveal styles: without scripting the content must stay
    // visible rather than sit at opacity 0 forever.
    root.classList.add('is-js');

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const timers: ReturnType<typeof setTimeout>[] = [];
    const later = (fn: () => void, ms: number) => timers.push(setTimeout(fn, ms));

    let observer: IntersectionObserver | undefined;
    const revealed = Array.from(root.querySelectorAll<HTMLElement>('.reveal'));
    if ('IntersectionObserver' in window && !reduced) {
      observer = new IntersectionObserver(
        (entries) => {
          for (const entry of entries) {
            if (entry.isIntersecting) {
              entry.target.classList.add('in');
              observer?.unobserve(entry.target);
            }
          }
        },
        {threshold: 0.15, rootMargin: '0px 0px -5% 0px'},
      );
      for (const el of revealed) observer.observe(el);
    } else {
      for (const el of revealed) el.classList.add('in');
    }

    const cleanup = () => {
      observer?.disconnect();
      for (const t of timers) clearTimeout(t);
    };

    const demo = root.querySelector<HTMLElement>('#demo');
    const planList = root.querySelector<HTMLElement>('#planList');
    const planChip = root.querySelector<HTMLElement>('#planChip');
    const approvalCard = root.querySelector<HTMLElement>('#approvalCard');
    if (!demo || !planList || !planChip || !approvalCard) return cleanup;

    const msgs = Array.from(demo.querySelectorAll<HTMLElement>('.dmsg'));
    const tasks = Array.from(planList.children) as HTMLElement[];

    const settle = () => {
      planChip.textContent = 'Plan approved';
      planChip.classList.add('ok');
      approvalCard.classList.add('approved');
      for (const task of tasks) {
        task.classList.remove('doing');
        task.classList.add('done');
      }
    };

    if (reduced) {
      settle();
      return cleanup;
    }

    // request -> plan -> plan approved -> gate -> approved -> done
    const beats: (() => void)[] = [
      () => msgs[0]?.classList.add('on'),
      () => msgs[1]?.classList.add('on'),
      () => {
        msgs[2]?.classList.add('on');
        planChip.textContent = 'Plan approved';
        planChip.classList.add('ok');
        tasks[0]?.classList.add('doing');
      },
      () => {
        tasks[0]?.classList.remove('doing');
        tasks[0]?.classList.add('done');
        tasks[1]?.classList.add('doing');
        msgs[3]?.classList.add('on');
      },
      () => {
        approvalCard.classList.add('approved');
        tasks[1]?.classList.remove('doing');
        tasks[1]?.classList.add('done');
        tasks[2]?.classList.add('doing');
      },
      () => {
        tasks[2]?.classList.remove('doing');
        tasks[2]?.classList.add('done');
        tasks[3]?.classList.add('done');
        msgs[4]?.classList.add('on');
      },
    ];

    let beat = 0;
    demo.classList.add('live');

    const rewind = () => {
      for (const msg of msgs) msg.classList.remove('on');
      for (const task of tasks) task.classList.remove('doing', 'done');
      planChip.textContent = 'Waiting for plan approval…';
      planChip.classList.remove('ok');
      approvalCard.classList.remove('approved');
      beat = 0;
    };

    const tick = () => {
      beats[beat]?.();
      beat += 1;
      if (beat < beats.length) {
        later(tick, STEP_DELAY);
      } else {
        later(() => {
          rewind();
          later(tick, 600);
        }, HOLD_AT_END);
      }
    };

    later(tick, 800);
    return cleanup;
  }, []);

  return (
    <Layout
      title={translate({id: 'home.meta.title', message: 'Agent as Workflow'})}
      description={translate({
        id: 'home.meta.description',
        message:
          'A2Flow rebuilds ITSM-style workflows around an AI agent. It plans the work as a task graph, pauses for the humans who must sign off, and executes the rest.',
      })}>
      <div className="a2flow-home" ref={rootRef}>
        {/* The standalone page kept these in its own sticky header, which the
            Docusaurus navbar has replaced; they belong to the page now. */}
        <nav className="page-nav" aria-label="Sections">
          <a href="#concept"><Translate id="home.nav.concept">{'Concept'}</Translate></a>
          <a href="#how"><Translate id="home.nav.how">{'How it works'}</Translate></a>
          <a href="#features"><Translate id="home.nav.features">{'Features'}</Translate></a>
          <a href="#architecture"><Translate id="home.nav.architecture">{'Architecture'}</Translate></a>
        </nav>

        {/* ============================================================ hero */}
        <section className="a2f-hero">
          <div className="wrap hero-grid">
            <div>
              <span className="eyebrow"><Translate id="home.hero.eyebrow">{'Agent as Workflow'}</Translate></span>
              <h1><Translate id="home.hero.title" values={{br: <br />, agent: <span className="grad-text"><Translate id="home.hero.title.agent">{'an agent'}</Translate></span>}}>{'The workflow engine{br}is now {agent}.'}</Translate></h1>
              <p className="hero-sub">
                <Translate id="home.hero.sub">{'A2Flow rebuilds ITSM-style workflows — service requests, change execution, announcements — around an AI agent. It plans the work as a task graph, pauses for the humans who must sign off, and executes the rest.'}</Translate>
              </p>
              <div className="hero-cta">
                <a className="btn btn-primary" href="https://github.com/kaitoy/a2flow">
                  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 .5C5.65.5.5 5.65.5 12c0 5.08 3.29 9.39 7.86 10.91.58.11.79-.25.79-.55 0-.27-.01-1.17-.02-2.12-3.2.7-3.87-1.36-3.87-1.36-.52-1.33-1.28-1.68-1.28-1.68-1.04-.71.08-.7.08-.7 1.15.08 1.76 1.19 1.76 1.19 1.03 1.76 2.69 1.25 3.35.96.1-.75.4-1.25.72-1.54-2.55-.29-5.23-1.28-5.23-5.68 0-1.26.45-2.28 1.19-3.09-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.17 1.18a11 11 0 0 1 5.77 0c2.2-1.49 3.16-1.18 3.16-1.18.63 1.59.24 2.76.12 3.05.74.81 1.19 1.83 1.19 3.09 0 4.41-2.69 5.38-5.25 5.67.41.35.77 1.05.77 2.12 0 1.53-.01 2.76-.01 3.14 0 .3.2.67.79.55A11.51 11.51 0 0 0 23.5 12C23.5 5.65 18.35.5 12 .5z"/></svg>
                  <Translate id="home.hero.cta.github">{'View on GitHub'}</Translate>
                </a>
                <a className="btn btn-ghost" href="#how"><Translate id="home.hero.cta.how">{'See how it works'}</Translate></a>
              </div>
              <div className="hero-tags">
                <span className="tag">Google ADK</span>
                <span className="tag">AG-UI protocol</span>
                <span className="tag">MCP tools</span>
                <span className="tag">Self-hosted</span>
              </div>
            </div>

            <div>
              {/* Self-playing workflow session. Decorative: the story is told in the copy. */}
              <div className="demo glass-strong" id="demo" aria-hidden="true">
                <div className="demo-titlebar">
                  <img className="demo-mark" src={logoUrl} alt="" />
                  Workflow session — Restart checkout pods
                  <span className="live">Live</span>
                </div>
                <div className="demo-body" id="demoBody">
                  <div className="dmsg from-user" data-step="1">
                    <div className="bubble user">Restart the checkout pods in prod — payments are timing out.</div>
                    <span className="a2f-avatar mika">M</span>
                  </div>
                  <div className="dmsg" data-step="2">
                    <span className="a2f-avatar bot">✦</span>
                    <div className="bubble agent">
                      <span className="who">Agent</span>
                      I read the <code>kubernetes-pod-restart</code> skill. Here is my plan:
                      <ul className="plan" id="planList">
                        <li><span className="tick"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5"/></svg></span>Identify the target deployment</li>
                        <li><span className="tick"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5"/></svg></span>Get approval — prod change</li>
                        <li><span className="tick"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5"/></svg></span>Rolling restart via kubectl</li>
                        <li><span className="tick"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5"/></svg></span>Verify the rollout</li>
                      </ul>
                      <span className="chip" id="planChip">Waiting for plan approval…</span>
                    </div>
                  </div>
                  <div className="dmsg demo-sys" data-step="3"><span><b>Mika</b> approved the plan</span></div>
                  <div className="dmsg" data-step="4">
                    <span className="a2f-avatar bot">✦</span>
                    <div className="approval" id="approvalCard">
                      <span className="ttl">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                        Approval required
                      </span>
                      <p>Rolling restart of <code>checkout</code> in <b>prod</b>. Approver: <b>Sam</b>.</p>
                      <span className="acts">
                        <span className="fbtn yes">Approve</span>
                        <span className="fbtn no">Reject</span>
                      </span>
                      <span className="decided">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5"/></svg>
                        Approved by Sam — “Change window confirmed.”
                      </span>
                    </div>
                  </div>
                  <div className="dmsg" data-step="6">
                    <span className="a2f-avatar bot">✦</span>
                    <div className="bubble agent">
                      <span className="who">Agent</span>
                      Rolling restart complete — 12/12 pods healthy. All tasks done.
                      <span className="chip ok" style={{marginTop: '.5rem'}}>Session completed 🔔</span>
                    </div>
                  </div>
                </div>
              </div>
              <p className="demo-caption"><Translate id="home.hero.demoCaption">{'A workflow session: the applicant, the approver, and the agent — one conversation.'}</Translate></p>
            </div>
          </div>
        </section>

        {/* ========================================================= concept */}
        <section className="section" id="concept">
          <div className="wrap">
            <div className="section-head reveal">
              <span className="eyebrow"><Translate id="home.concept.eyebrow">{'The concept'}</Translate></span>
              <h2><Translate id="home.concept.title" values={{reimagined: <span className="grad-text"><Translate id="home.concept.title.reimagined">{'reimagined'}</Translate></span>}}>{'ITSM workflows, {reimagined}'}</Translate></h2>
              <p>
                <Translate id="home.concept.lead">{'Classic workflow engines encode a process as rigid forms, ticket queues, and handoffs between people. Most of the elapsed time is waiting. A2Flow keeps the two things that matter — the procedure and the approvals — and hands everything in between to an agent.'}</Translate>
              </p>
            </div>
            <div className="contrast">
              <div className="contrast-card glass past reveal">
                <h3><Translate id="home.concept.past.title">{'The ticket pipeline'}</Translate></h3>
                <p className="sub"><Translate id="home.concept.past.sub">{'Process as software: fixed forms, fixed states, humans as glue.'}</Translate></p>
                <ul className="flow-steps">
                  <li><span className="dot"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9h10M7 13h6"/></svg></span><span><b><Translate id="home.concept.past.form">{'Fill in the form'}</Translate></b><span className="note"><Translate id="home.concept.past.form.note">{'One field wrong and it bounces back.'}</Translate></span></span></li>
                  <li><span className="dot"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg></span><span><b><Translate id="home.concept.past.queue">{'Wait in the queue'}</Translate></b><span className="note"><Translate id="home.concept.past.queue.note">{'Your request is #14 in line.'}</Translate></span></span></li>
                  <li><span className="dot"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M17 3h4v4M21 3l-7 7M7 21H3v-4M3 21l7-7"/></svg></span><span><b><Translate id="home.concept.past.handoff">{'Hand off between teams'}</Translate></b><span className="note"><Translate id="home.concept.past.handoff.note">{'Context is lost at every hop.'}</Translate></span></span></li>
                  <li><span className="dot"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M4 4h16v12H5.2L4 17.2V4z"/><path d="M8 8h8M8 12h5"/></svg></span><span><b><Translate id="home.concept.past.chase">{'Chase the status'}</Translate></b><span className="note"><Translate id="home.concept.past.chase.note">{'“Any update on my ticket?”'}</Translate></span></span></li>
                </ul>
              </div>
              <div className="contrast-card glass next reveal">
                <h3 className="grad-text"><Translate id="home.concept.next.title">{'The agent workflow'}</Translate></h3>
                <p className="sub"><Translate id="home.concept.next.sub">{'Process as conversation: the agent drives, humans decide.'}</Translate></p>
                <ul className="flow-steps">
                  <li><span className="dot"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-8.5 8.5c-1.6 0-3.1-.4-4.4-1.2L3 20l1.2-5.1A8.5 8.5 0 1 1 21 11.5z"/></svg></span><span><b><Translate id="home.concept.next.intent">{'Describe the intent in chat'}</Translate></b><span className="note"><Translate id="home.concept.next.intent.note">{'No form. The Skill knows what to ask.'}</Translate></span></span></li>
                  <li><span className="dot"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="5" cy="6" r="2.2"/><circle cx="19" cy="6" r="2.2"/><circle cx="12" cy="18" r="2.2"/><path d="M6.5 7.5 10.5 16M17.5 7.5 13.5 16"/></svg></span><span><b><Translate id="home.concept.next.plan">{'The agent plans a task graph'}</Translate></b><span className="note"><Translate id="home.concept.next.plan.note">{'Concrete steps with dependencies — visible to everyone.'}</Translate></span></span></li>
                  <li><span className="dot"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg></span><span><b><Translate id="home.concept.next.approve">{'Humans approve the moments that matter'}</Translate></b><span className="note"><Translate id="home.concept.next.approve.note">{'The plan itself, and every destructive step.'}</Translate></span></span></li>
                  <li><span className="dot"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><polygon points="6 3 20 12 6 21 6 3"/></svg></span><span><b><Translate id="home.concept.next.execute">{'The agent executes and verifies'}</Translate></b><span className="note"><Translate id="home.concept.next.execute.note">{'Live progress in the same conversation.'}</Translate></span></span></li>
                </ul>
              </div>
            </div>
            <div className="concept-note glass reveal">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M15 3H9a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2V8l-2-5z"/><path d="M15 3v5h2M10 13h4M10 17h4"/></svg>
              <span>
                <Translate id="home.concept.note" values={{skill: <b><Translate id="home.concept.note.skill" values={{file: <code>SKILL.md</code>}}>{'Agent Skill — a {file} file in a Git repository'}</Translate></b>}}>{'The procedure itself is not code locked inside a workflow engine. It is an {skill} — versioned, reviewable, and readable by anyone on the team.'}</Translate>
              </span>
            </div>
          </div>
        </section>

        {/* ============================================================= how */}
        <section className="section" id="how">
          <div className="wrap">
            <div className="section-head reveal">
              <span className="eyebrow"><Translate id="home.how.eyebrow">{'How it works'}</Translate></span>
              <h2><Translate id="home.how.title" values={{execute: <span className="grad-text"><Translate id="home.how.title.execute">{'Execute.'}</Translate></span>}}>{'Plan. Approve. {execute}'}</Translate></h2>
              <p>
                <Translate id="home.how.lead">{'Every workflow session runs under the same two-phase policy: nothing executes until a human has seen the plan, and nothing destructive executes until the designated approver has said yes.'}</Translate>
              </p>
            </div>
            <div className="how-grid">
              <div className="steps">
                <div className="step glass reveal">
                  <span className="n"><Translate id="home.how.step1.label">{'STEP 1 — PLAN'}</Translate></span>
                  <h3><Translate id="home.how.step1.title">{'The agent turns intent into a task graph'}</Translate></h3>
                  <p>
                    <Translate id="home.how.step1.body">{'It reads the linked Agent Skill, breaks the request into WorkflowTasks with explicit dependencies, and registers the whole DAG in one call — cycle detection included. Nothing runs yet.'}</Translate>
                  </p>
                </div>
                <div className="step glass reveal">
                  <span className="n"><Translate id="home.how.step2.label">{'STEP 2 — APPROVE'}</Translate></span>
                  <h3><Translate id="home.how.step2.title">{'Humans gate the moments that matter'}</Translate></h3>
                  <p>
                    <Translate id="home.how.step2.body" values={{approver: <em><Translate id="home.how.step2.body.approver">{'designated approver'}</Translate></em>, forbidden: <code>403</code>}}>{'The session owner approves the plan before execution starts. Destructive steps gate again on a {approver}: Approve / Reject controls render right in the chat, and only that person can resolve them — anyone else gets a {forbidden}.'}</Translate>
                  </p>
                </div>
                <div className="step glass reveal">
                  <span className="n"><Translate id="home.how.step3.label">{'STEP 3 — EXECUTE'}</Translate></span>
                  <h3><Translate id="home.how.step3.title">{'The agent walks the graph'}</Translate></h3>
                  <p>
                    <Translate id="home.how.step3.body" values={{statuses: <code>pending → in_progress → completed</code>}}>{'Tasks move {statuses} in dependency order, calling only the MCP tools bound to the current task. Everyone watches live, in a table or as a graph.'}</Translate>
                  </p>
                </div>
              </div>
              <div className="dag-panel glass-strong reveal">
                <div className="panel-title">
                  <span>WorkflowTasks</span>
                  <span className="views"><span>Table</span> · <span className="cur">Graph</span></span>
                </div>
                <svg className="dag-svg" viewBox="0 0 440 340" role="img" aria-label="A task graph: identify target and notify channel completed, prod approval gated, rolling restart in progress, verify rollout pending.">
                  {/* edges */}
                  <path className="edge" d="M220 66 C 220 84, 130 88, 128 106"/>
                  <path className="edge" d="M220 66 C 220 84, 310 88, 312 106"/>
                  <path className="edge" d="M128 162 C 128 180, 216 184, 218 202"/>
                  <path className="edge" d="M220 258 C 220 270, 220 274, 220 286"/>
                  {/* root: completed */}
                  <g>
                    <rect className="node-box done-box" x="130" y="10" width="180" height="56" rx="14"/>
                    <circle cx="156" cy="38" r="9" fill="var(--a2f-success)"/>
                    <path d="m152 38 3 3 5.5-6" stroke="#fff" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
                    <text className="node-label" x="174" y="35">Identify target</text>
                    <text className="node-sub" x="174" y="50" fill="var(--a2f-success)">COMPLETED</text>
                  </g>
                  {/* left branch: approval gate */}
                  <g>
                    <rect className="node-box gate-box" x="38" y="106" width="180" height="56" rx="14"/>
                    <path d="M64 29.5v6.8c0 5-4.5 7.4-6.8 8.2-2.3-.8-6.8-3.2-6.8-8.2v-6.8l6.8-2.5 6.8 2.5z" transform="translate(6 101)" fill="none" stroke="var(--a2f-secondary)" strokeWidth="1.8" strokeLinejoin="round"/>
                    <text className="node-label" x="86" y="131">Approve prod change</text>
                    <text className="node-sub" x="86" y="146" fill="var(--a2f-secondary)">WAITING · SAM</text>
                  </g>
                  {/* right branch: completed */}
                  <g>
                    <rect className="node-box done-box" x="222" y="106" width="180" height="56" rx="14"/>
                    <circle cx="248" cy="134" r="9" fill="var(--a2f-success)"/>
                    <path d="m244 134 3 3 5.5-6" stroke="#fff" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
                    <text className="node-label" x="266" y="131">Notify #ops channel</text>
                    <text className="node-sub" x="266" y="146" fill="var(--a2f-success)">COMPLETED</text>
                  </g>
                  {/* in progress */}
                  <g>
                    <rect className="node-box doing-box" x="130" y="202" width="180" height="56" rx="14"/>
                    <circle className="doing-ring" cx="156" cy="230" r="9" fill="none" stroke="var(--a2f-accent-bright)" strokeWidth="2.5"/>
                    <circle cx="156" cy="230" r="3.5" fill="var(--a2f-accent-bright)"/>
                    <text className="node-label" x="174" y="227">Rolling restart</text>
                    <text className="node-sub" x="174" y="242" fill="var(--a2f-accent-bright)">IN PROGRESS</text>
                  </g>
                  {/* pending */}
                  <g opacity="0.65">
                    <rect className="node-box pend-box" x="130" y="286" width="180" height="46" rx="14"/>
                    <circle cx="156" cy="309" r="8" fill="none" stroke="var(--a2f-muted)" strokeWidth="1.8" opacity="0.6"/>
                    <text className="node-label" x="174" y="306">Verify rollout</text>
                    <text className="node-sub" x="174" y="320" fill="var(--a2f-muted)">PENDING</text>
                  </g>
                </svg>
                <div className="dag-legend">
                  <span><i style={{background: 'var(--a2f-success)'}}></i>completed</span>
                  <span><i style={{background: 'var(--a2f-accent-bright)'}}></i>in progress</span>
                  <span><i style={{background: 'var(--a2f-secondary)'}}></i>approval gate</span>
                  <span><i style={{border: '1.5px dashed var(--a2f-muted)', background: 'transparent'}}></i>pending</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* =========================================================== roles */}
        <section className="section" id="teams">
          <div className="wrap">
            <div className="section-head reveal">
              <span className="eyebrow"><Translate id="home.teams.eyebrow">{'Built for teams'}</Translate></span>
              <h2><Translate id="home.teams.title" values={{conversation: <span className="grad-text"><Translate id="home.teams.title.conversation">{'one conversation'}</Translate></span>}}>{'Three roles, {conversation}'}</Translate></h2>
              <p>
                <Translate id="home.teams.lead">{'A workflow session is a shared chat. The applicant, the approver, and the agent all post into the same thread — no side channels, no “any update on my ticket?”'}</Translate>
              </p>
            </div>
            <div className="roles">
              <div className="role-card glass reveal">
                <span className="a2f-avatar mika">M</span>
                <h3><Translate id="home.teams.applicant.title">{'The applicant'}</Translate></h3>
                <p>
                  <Translate id="home.teams.applicant.body">{'Owns the session. Describes the intent, answers the agent\'s questions, and approves the plan before anything runs.'}</Translate>
                </p>
              </div>
              <div className="role-card glass reveal">
                <span className="a2f-avatar sam">S</span>
                <h3><Translate id="home.teams.approver.title">{'The approver'}</Translate></h3>
                <p>
                  <Translate id="home.teams.approver.body">{'Gets a notification, opens the session, and decides right in the chat — with a comment. Only the designated approver can resolve an approval.'}</Translate>
                </p>
              </div>
              <div className="role-card glass reveal">
                <span className="a2f-avatar bot">✦</span>
                <h3><Translate id="home.teams.agent.title">{'The agent'}</Translate></h3>
                <p>
                  <Translate id="home.teams.agent.body">{'Plans the task graph, requests approvals at the right moments, executes each step per the Skill, and reports progress as it goes.'}</Translate>
                </p>
              </div>
            </div>
            <div className="trust-row">
              <div className="trust-card glass reveal">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/></svg>
                <div>
                  <h4><Translate id="home.teams.trust.notifications.title">{'Notifications that carry you to the decision'}</Translate></h4>
                  <p>
                    <Translate id="home.teams.trust.notifications.body">{'Approval requests and session completions land in each user\'s notification bell and deep-link straight into the relevant conversation.'}</Translate>
                  </p>
                </div>
              </div>
              <div className="trust-card glass reveal">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M15 3H9a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2V8l-2-5z"/><path d="M15 3v5h2"/><path d="m9.5 14 1.7 1.7L14.5 12"/></svg>
                <div>
                  <h4><Translate id="home.teams.trust.audit.title">{'An audit trail on every approval'}</Translate></h4>
                  <p>
                    <Translate id="home.teams.trust.audit.body">{'Who approved, what they wrote, and exactly when — persisted on the approval record and browsable in the admin console.'}</Translate>
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ======================================================== features */}
        <section className="section" id="features">
          <div className="wrap">
            <div className="section-head reveal">
              <span className="eyebrow"><Translate id="home.features.eyebrow">{'Features'}</Translate></span>
              <h2><Translate id="home.features.title" values={{nothing: <span className="grad-text"><Translate id="home.features.title.nothing">{'nothing it doesn\'t'}</Translate></span>}}>{'Everything a workflow needs, {nothing}'}</Translate></h2>
            </div>
            <div className="features">
              <div className="feature glass reveal">
                <span className="fic"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.4 5.4 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4"/><path d="M9 18c-4.51 2-5-2-7-2"/></svg></span>
                <h3><Translate id="home.features.skills.title">{'Agent Skills in Git'}</Translate></h3>
                <p>
                  <Translate id="home.features.skills.body" values={{file: <code>SKILL.md</code>}}>{'Procedures live as {file} files in Git repositories, cloned on first run. Version them, review them, read them — like any other code.'}</Translate>
                </p>
              </div>
              <div className="feature glass reveal">
                <span className="fic"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="5" cy="6" r="2.2"/><circle cx="19" cy="6" r="2.2"/><circle cx="12" cy="18" r="2.2"/><path d="M6.5 7.5 10.5 16M17.5 7.5 13.5 16"/></svg></span>
                <h3><Translate id="home.features.graph.title">{'A live task graph'}</Translate></h3>
                <p>
                  <Translate id="home.features.graph.body">{'Tasks form a real DAG — dependencies enforced, cycles rejected — and render as a sortable table or an auto-laid-out graph, updating as the agent works.'}</Translate>
                </p>
              </div>
              <div className="feature glass reveal">
                <span className="fic"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg></span>
                <h3><Translate id="home.features.gates.title">{'Approval gates mid-run'}</Translate></h3>
                <p>
                  <Translate id="home.features.gates.body">{'Before a destructive step, the agent requests approval from a specific user and pauses. Approve / Reject buttons appear in the chat — for that user only.'}</Translate>
                </p>
              </div>
              <div className="feature glass reveal">
                <span className="fic"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/></svg></span>
                <h3><Translate id="home.features.mcp.title">{'MCP tools, scoped per task'}</Translate></h3>
                <p>
                  <Translate id="home.features.mcp.body">{'Register remote MCP servers, and the agent binds only the tools each task needs at plan time. At run time, a task can call nothing but its own tools.'}</Translate>
                </p>
              </div>
              <div className="feature glass reveal">
                <span className="fic"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="4" width="18" height="14" rx="2"/><path d="M8 21h8M12 18v3M7 9h4v4H7zM14 9h3M14 13h3"/></svg></span>
                <h3><Translate id="home.features.a2ui.title">{'Rich UI inside the chat'}</Translate></h3>
                <p>
                  <Translate id="home.features.a2ui.body">{'Through the A2UI protocol the agent renders buttons, forms, and cards inline — and your clicks flow back into the run as tool results.'}</Translate>
                </p>
              </div>
              <div className="feature glass reveal">
                <span className="fic"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2a7 7 0 0 1 7 7c0 2.4-1.2 4.5-3 5.7V17a2 2 0 0 1-2 2h-4a2 2 0 0 1-2-2v-2.3C6.2 13.5 5 11.4 5 9a7 7 0 0 1 7-7z"/><path d="M9 21h6"/></svg></span>
                <h3><Translate id="home.features.llm.title">{'Bring your own LLM'}</Translate></h3>
                <p>
                  <Translate id="home.features.llm.body">{'Gemini by default; OpenAI and Anthropic models via LiteLLM. Swapping providers is one environment variable.'}</Translate>
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* ==================================================== architecture */}
        <section className="section" id="architecture">
          <div className="wrap">
            <div className="section-head reveal">
              <span className="eyebrow"><Translate id="home.architecture.eyebrow">{'Under the hood'}</Translate></span>
              <h2><Translate id="home.architecture.title" values={{stack: <span className="grad-text"><Translate id="home.architecture.title.stack">{'stack'}</Translate></span>}}>{'An open-protocol {stack}'}</Translate></h2>
              <p>
                <Translate id="home.architecture.lead">{'A Next.js chat UI streams AG-UI events from a FastAPI backend that hosts a Google ADK agent. Skills come from Git, tools come from MCP servers, and one relational database holds it all.'}</Translate>
              </p>
            </div>
            <div className="arch glass reveal">
              <div className="arch-flow">
                <div className="arch-node glass-strong">
                  <b>Next.js 16 chat UI</b>
                  <span>React 19 · A2UI renderer</span>
                </div>
                <div className="arch-link">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M8 3 4 7l4 4"/><path d="M4 7h16"/><path d="m16 21 4-4-4-4"/><path d="M20 17H4"/></svg>
                  AG-UI · SSE
                </div>
                <div className="arch-node glass-strong">
                  <b>FastAPI + Google ADK</b>
                  <span>plan-then-execute agent</span>
                </div>
                <div className="arch-link">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14"/><path d="m13 6 6 6-6 6"/></svg>
                  TOOLS
                </div>
                <div className="arch-side">
                  <div className="arch-node glass-strong">
                    <b>MCP servers</b>
                    <span>streamable HTTP</span>
                  </div>
                  <div className="arch-node glass-strong">
                    <b>Skills in Git</b>
                    <span>SKILL.md repos</span>
                  </div>
                  <div className="arch-node glass-strong">
                    <b>PostgreSQL / SQLite</b>
                    <span>sessions · tasks · approvals</span>
                  </div>
                </div>
              </div>
              <div className="stack-chips">
                <span className="tag">Next.js 16</span>
                <span className="tag">React 19</span>
                <span className="tag">Tailwind CSS 4</span>
                <span className="tag">FastAPI</span>
                <span className="tag">Google ADK</span>
                <span className="tag">ag-ui-adk</span>
                <span className="tag">LiteLLM</span>
                <span className="tag">SQLModel</span>
                <span className="tag">Docker Compose</span>
              </div>
            </div>
          </div>
        </section>

        {/* ============================================================ cta */}
        <section className="cta-final">
          <div className="wrap">
            <div className="reveal">
              <span className="eyebrow"><Translate id="home.cta.eyebrow">{'Get started'}</Translate></span>
              <h2><Translate id="home.cta.title" values={{machine: <span className="grad-text"><Translate id="home.cta.title.machine">{'on your machine'}</Translate></span>}}>{'Run it {machine}'}</Translate></h2>
              <p>
                <Translate id="home.cta.lead">{'The whole stack — PostgreSQL, backend, frontend — comes up with Docker Compose. Bring a Google API key and you\'re two commands away from your first workflow.'}</Translate>
              </p>
            </div>
            <div className="terminal reveal">
              <div className="terminal-bar" aria-hidden="true"><i></i><i></i><i></i></div>
              <pre><code><span className="p">$</span> git clone https://github.com/kaitoy/a2flow.git &amp;&amp; cd a2flow
      <span className="p">$</span> echo GOOGLE_API_KEY=your_google_api_key_here &gt; .env
      <span className="p">$</span> docker compose up --build
      <span className="c"># open http://localhost:3000</span></code></pre>
            </div>
            <div className="reveal">
              <a className="btn btn-primary" href="https://github.com/kaitoy/a2flow">
                <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 .5C5.65.5.5 5.65.5 12c0 5.08 3.29 9.39 7.86 10.91.58.11.79-.25.79-.55 0-.27-.01-1.17-.02-2.12-3.2.7-3.87-1.36-3.87-1.36-.52-1.33-1.28-1.68-1.28-1.68-1.04-.71.08-.7.08-.7 1.15.08 1.76 1.19 1.76 1.19 1.03 1.76 2.69 1.25 3.35.96.1-.75.4-1.25.72-1.54-2.55-.29-5.23-1.28-5.23-5.68 0-1.26.45-2.28 1.19-3.09-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.17 1.18a11 11 0 0 1 5.77 0c2.2-1.49 3.16-1.18 3.16-1.18.63 1.59.24 2.76.12 3.05.74.81 1.19 1.83 1.19 3.09 0 4.41-2.69 5.38-5.25 5.67.41.35.77 1.05.77 2.12 0 1.53-.01 2.76-.01 3.14 0 .3.2.67.79.55A11.51 11.51 0 0 0 23.5 12C23.5 5.65 18.35.5 12 .5z"/></svg>
                Star on GitHub
              </a>
            </div>
          </div>
        </section>
      </div>
    </Layout>
  );
}
