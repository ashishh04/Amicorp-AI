// UDAP landing page (index.html): content, the hero diagram, tabs and scroll effects.
// Where the "Sign in" buttons go: the portal's sign-in page when the portal serves this page
// (/udap/), or the local portal when the page is opened as a file. '' hides them.
const PORTAL_URL = location.protocol === 'file:' ? 'http://localhost:4200/login' : '../login';

// ------------------------------------------------------------------ content
const SOURCES = [
  { n: '5 Series', d: 'Core entity and fund administration', saas: false },
  { n: 'CARE', d: 'Cases and workflow, with documents', saas: false },
  { n: 'Paxus', d: 'Fund accounting', saas: false },
  { n: 'Flexcube', d: 'Core banking', saas: false },
  { n: 'Maconomy', d: 'ERP and finance', saas: true },
  { n: 'Pega', d: 'AmiPortal payment requests', saas: true },
  { n: 'Zoho CRM', d: 'Client relationship management', saas: true },
  { n: 'Valuefy', d: 'Wealth platform', saas: true },
  { n: 'AsamcoLMS', d: 'Loan management', saas: true },
];

const ICON = {
  compare: '<path d="M4 4h7v16H4zM13 4h7v16h-7z"/><path d="M7 9h1M7 13h1M16 9h1M16 13h1"/>',
  bank: '<path d="M3 9l9-5 9 5"/><path d="M5 9v9M9 9v9M15 9v9M19 9v9M3 20h18"/>',
  shield: '<path d="M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6z"/><path d="M8 12h2l1.5-3 2 6 1.5-3h1"/>',
  chart: '<path d="M4 19h16"/><path d="M5 15l4-4 3 3 6-7"/><path d="M15 7h3v3"/>',
  flag: '<path d="M5 21V4"/><path d="M5 4h11l-2 4 2 4H5"/>',
  plus: '<circle cx="12" cy="12" r="9"/><path d="M12 8v8M8 12h8"/>',
};

const USE_CASES = [
  {
    name: 'Data validation and inconsistency',
    icon: 'compare',
    tone: '',
    live: 'Live at M1 · week 10',
    intro:
      'Scans compare the systems of record and turn each discrepancy into one Work Card, never two. The first use case live, and the test of the whole framework.',
    trigger: 'A discrepancy found by a scan',
    ai: 'Evidence summary and a proposed correction',
    human: 'Data team expert',
    writes: 'The systems of record, through write-back',
  },
  {
    name: 'Bank statement processing',
    icon: 'bank',
    tone: 'violet',
    live: 'Live at M2 · week 12',
    flagship: true,
    intro:
      'Statements in many regional formats are extracted, checked field by field and reconciled. Low confidence becomes a reviewed exception, never a silent error.',
    trigger: 'A bank statement arrives',
    ai: 'Extraction, with a confidence cross-check',
    human: 'An operator prepares; a checker approves',
    writes: 'Exchange folders; status in CARE and 5 Series',
  },
  {
    name: 'Transaction monitoring (AML)',
    icon: 'shield',
    tone: 'rose',
    live: 'Acceptance at M4 · week 19',
    intro:
      'Three gates check every payment in real time: entry thresholds, the client profile and live screening. A gate that cannot decide holds the payment for a person.',
    trigger: 'A payment request or a statement line',
    ai: "Reads the client's free-text profile and summarises",
    human: 'A compliance officer; the MLRO on escalation',
    writes: 'CARE audit file; a 5 Series incident',
  },
  {
    name: 'NAV statement validation',
    icon: 'chart',
    tone: 'green',
    live: 'Acceptance at M4 · week 19',
    intro:
      "The valuation date, the NAV movement against the fund's tolerance and the share register are checked. Only exceptions reach a fund accountant.",
    trigger: 'A NAV statement arrives',
    ai: 'Extraction and a summary',
    human: 'A fund accountant, on exceptions',
    writes: 'The Valuefy feed and downstream',
  },
  {
    name: 'Violation-triggered Work Cards',
    icon: 'flag',
    tone: 'amber',
    live: 'Live at M6 · week 24',
    intro:
      'Data policies run on the governed Gold layer. Each breach becomes a Work Card with a proposed correction for the responsible expert.',
    trigger: 'A policy violation on Gold',
    ai: 'Proposes the correction',
    human: 'The responsible expert',
    writes: 'CARE and 5 Series',
  },
  {
    name: 'A sixth use case, chosen with Amicorp',
    icon: 'plus',
    tone: '',
    live: 'Live at M6 · week 24',
    intro:
      'Selected with Amicorp at week 18 against agreed criteria, and delivered on the same framework, with the same controls and audit trail.',
    trigger: 'Agreed at week 18',
    ai: 'Agreed with the use case',
    human: 'As the selection criteria require',
    writes: 'Agreed with the use case',
  },
];

const svgIcon = (body, size = 24) =>
  `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`;
const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

// ------------------------------------------------------------------ hero diagram
(function buildFlow() {
  const NS = 'http://www.w3.org/2000/svg';
  const el = (name, attrs, parent) => {
    const node = document.createElementNS(NS, name);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    parent.appendChild(node);
    return node;
  };
  const wires = document.getElementById('wires');
  const particles = document.getElementById('particles');
  const sources = document.getElementById('sources');
  const outputs = document.getElementById('outputs');
  const motion = !window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  SOURCES.forEach((s, i) => {
    const y = 14 + i * 49.5;
    const cy = y + 16;
    const ty = 185 + i * 11.5;
    const id = 'in' + i;
    el('path', { id, class: 'wire', d: `M130 ${cy} C196 ${cy} 206 ${ty} 262 ${ty}` }, wires);
    const g = el('g', { class: 'src' }, sources);
    el('rect', { x: 6, y, width: 124, height: 32, rx: 16 }, g);
    el('text', { x: 68, y: y + 20.5, 'text-anchor': 'middle' }, g).textContent = s.n;
    if (motion) {
      const dot = el('circle', { class: 'particle', r: 4.5, fill: 'url(#dotIn)' }, particles);
      const anim = el('animateMotion', { dur: (2.6 + (i % 4) * 0.45) + 's', repeatCount: 'indefinite', begin: (-i * 0.37) + 's' }, dot);
      el('mpath', { href: '#' + id }, anim);
    }
  });

  ['Work Card portal', 'Twenty dashboards', 'Governed write-back'].forEach((label, j) => {
    const y = 133 + j * 78;
    const cy = y + 20;
    const sy = 205 + j * 26;
    const id = 'out' + j;
    el('path', { id, class: 'wire wire-out', d: `M398 ${sy} C445 ${sy} 455 ${cy} 500 ${cy}` }, wires);
    const g = el('g', { class: 'out' }, outputs);
    el('rect', { x: 500, y, width: 134, height: 40, rx: 12 }, g);
    el('text', { x: 567, y: y + 24.5, 'text-anchor': 'middle' }, g).textContent = label;
    if (motion) {
      const dot = el('circle', { class: 'particle', r: 4.5, fill: 'url(#dotOut)' }, particles);
      const anim = el('animateMotion', { dur: '2.2s', repeatCount: 'indefinite', begin: (-j * 0.7) + 's' }, dot);
      el('mpath', { href: '#' + id }, anim);
    }
  });
})();

// ------------------------------------------------------------------ source systems
document.querySelector('.systems').innerHTML = SOURCES.map(
  (s, i) => `
    <article class="card sys reveal${s.saas ? ' saas' : ''}${i % 3 ? ' d-' + (i % 3) * 60 : ''}">
      <span class="mono" aria-hidden="true">${esc(s.n.replace(/[^A-Za-z0-9]/g, '').slice(0, 2).toUpperCase())}</span>
      <span><strong>${esc(s.n)}</strong><small>${esc(s.d)}</small>
      <em>${s.saas ? 'SaaS' : 'Huawei Cloud HK'}</em></span>
    </article>`,
).join('');

// ------------------------------------------------------------------ use-case tabs
(function buildUseCases() {
  const tabs = document.querySelector('.uc-tabs');
  const panels = document.querySelector('.uc-panels');
  tabs.innerHTML = USE_CASES.map(
    (u, i) => `
      <button class="uc-tab" role="tab" id="uc-tab-${i}" aria-controls="uc-panel-${i}" aria-selected="${i === 1}" tabindex="${i === 1 ? 0 : -1}">
        <span class="icon ${u.tone}">${svgIcon(ICON[u.icon], 22)}</span>
        <span><strong>${esc(u.name)}</strong><small>${esc(u.live)}</small></span>
      </button>`,
  ).join('');
  panels.innerHTML = USE_CASES.map(
    (u, i) => `
      <div class="uc-panel" role="tabpanel" id="uc-panel-${i}" aria-labelledby="uc-tab-${i}" ${i === 1 ? '' : 'hidden'}>
        <div class="uc-title">
          <span class="icon ${u.tone}">${svgIcon(ICON[u.icon], 26)}</span>
          <h3>${esc(u.name)}</h3>
          ${u.flagship ? '<span class="flag">Flagship</span>' : ''}
          <span class="live">${esc(u.live)}</span>
        </div>
        <p>${esc(u.intro)}</p>
        <div class="facts">
          <div class="fact"><span><i class="c-blue"></i>Trigger</span><p>${esc(u.trigger)}</p></div>
          <div class="fact"><span><i class="c-violet"></i>What AI does</span><p>${esc(u.ai)}</p></div>
          <div class="fact"><span><i class="c-green"></i>Who decides</span><p>${esc(u.human)}</p></div>
          <div class="fact"><span><i class="c-amber"></i>Writes to</span><p>${esc(u.writes)}</p></div>
        </div>
      </div>`,
  ).join('');

  const all = [...tabs.querySelectorAll('[role=tab]')];
  const select = (i, focus) => {
    all.forEach((t, j) => {
      const on = i === j;
      t.setAttribute('aria-selected', on);
      t.tabIndex = on ? 0 : -1;
      const panel = document.getElementById('uc-panel-' + j);
      panel.hidden = !on;
      panel.classList.toggle('show', on);
    });
    if (focus) all[i].focus();
  };
  all.forEach((t, i) => {
    t.addEventListener('click', () => select(i, false));
    t.addEventListener('keydown', (e) => {
      const step = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 }[e.key];
      if (step) {
        e.preventDefault();
        select((i + step + all.length) % all.length, true);
      } else if (e.key === 'Home' || e.key === 'End') {
        e.preventDefault();
        select(e.key === 'Home' ? 0 : all.length - 1, true);
      }
    });
  });
})();

// ------------------------------------------------------------------ page behaviour
document.documentElement.classList.add('js');
document.getElementById('year').textContent = new Date().getFullYear();

document.querySelectorAll('[data-portal]').forEach((a) => {
  if (PORTAL_URL) a.href = PORTAL_URL;
  else a.remove();
});

const nav = document.getElementById('nav');
const onScroll = () => nav.classList.toggle('solid', window.scrollY > 24);
onScroll();
window.addEventListener('scroll', onScroll, { passive: true });

const menu = document.getElementById('menu');
const menuBtn = document.querySelector('.menu-btn');
menuBtn.addEventListener('click', () => {
  const open = menu.classList.toggle('open');
  menuBtn.setAttribute('aria-expanded', open);
  nav.classList.add('solid');
});
menu.addEventListener('click', (e) => {
  if (e.target.closest('a')) {
    menu.classList.remove('open');
    menuBtn.setAttribute('aria-expanded', 'false');
  }
});

// Count the figures up the first time they come into view.
const countUp = (node) => {
  const target = Number(node.dataset.count);
  const start = performance.now();
  const tick = (now) => {
    const t = Math.min(1, (now - start) / 1400);
    node.textContent = Math.round(target * (1 - Math.pow(1 - t, 3)));
    if (t < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
};

const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const reveal = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('in');
      if (!reduce) entry.target.querySelectorAll('[data-count]').forEach(countUp);
      reveal.unobserve(entry.target);
    });
  },
  { threshold: 0.12, rootMargin: '0px 0px -40px 0px' },
);
document.querySelectorAll('.reveal').forEach((n) => reveal.observe(n));

// The figures sit on the first screen, so they never fade in; they only count up once.
const figures = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      if (!reduce) entry.target.querySelectorAll('[data-count]').forEach(countUp);
      figures.unobserve(entry.target);
    });
  },
  { threshold: 0.4 },
);
figures.observe(document.querySelector('.stats-grid'));

// Highlight the section in view in the menu.
const links = [...menu.querySelectorAll('a')];
const spy = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      links.forEach((a) => a.classList.toggle('active', a.getAttribute('href') === '#' + entry.target.id));
    });
  },
  { rootMargin: '-45% 0px -50% 0px' },
);
['platform', 'how', 'use-cases', 'data', 'security', 'roadmap'].forEach((id) =>
  spy.observe(document.getElementById(id)),
);
