'use strict';
/* LVAEP tutor reporting prototype — single-page app (no build step, no dependencies). */

const $ = (sel, el = document) => el.querySelector(sel);
const app = $('#app');
const topbar = $('#topbar');
const dialog = $('#dialog');
const state = { me: null, unread: 0, meta: null, overview: null, ovFilter: 'all', ovSearch: '' };

/* ---------- safe HTML templating: every interpolation is escaped unless wrapped in raw() ---------- */
class Safe { constructor(s) { this.s = s; } toString() { return this.s; } }
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const raw = (s) => new Safe(s);
const fmtv = (v) => (v == null || v === false ? '' : v instanceof Safe ? v.s : Array.isArray(v) ? v.map(fmtv).join('') : esc(v));
const html = (strings, ...vals) => new Safe(strings.reduce((o, s, i) => o + s + (i < vals.length ? fmtv(vals[i]) : ''), ''));

const ICON = {
  bell: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>',
  logout: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/></svg>',
  cal: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>',
  pin: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/></svg>',
  alert: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/></svg>',
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>',
  clock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>',
  print: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9V2h12v7"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><path d="M6 14h12v8H6z"/></svg>',
  download: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/></svg>',
  send: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/></svg>',
  plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>',
};
const icon = (name) => raw(ICON[name]);

/* ---------- formatting ---------- */
const parseD = (s) => { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d || 1); };
const isoD = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const fmtDate = (s, opts = { weekday: 'short', month: 'short', day: 'numeric' }) => (s ? parseD(s).toLocaleDateString('en-US', opts) : '');
const monthLabel = (m) => parseD(`${m}-01`).toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
const monthShort = (m) => parseD(`${m}-01`).toLocaleDateString('en-US', { month: 'long' });
const shiftMonth = (m, n) => { const d = parseD(`${m}-01`); d.setMonth(d.getMonth() + n); return isoD(d).slice(0, 7); };
const monthEnd = (m) => { const d = parseD(`${m}-01`); d.setMonth(d.getMonth() + 1); d.setDate(0); return isoD(d); };
const today = () => state.meta.today;
const thisMonth = () => today().slice(0, 7);
const fmtH = (h) => String(Math.round(Number(h || 0) * 100) / 100);
const fmtDT = (s) => (s ? new Date(s.replace(' ', 'T')).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : '');
const isStaff = () => state.me && state.me.role === 'staff';
const STATUS = { not_started: 'Not started', in_progress: 'In progress', returned: 'Needs changes', submitted: 'Submitted', reviewed: 'Reviewed' };
const chip = (s) => html`<span class="chip ${s}">${STATUS[s] || s}</span>`;
const studentChip = (s) => (s === 'active' ? '' : html` <span class="chip ${s}">${s === 'paused' ? 'Paused' : 'Dropped'}</span>`);

/* ---------- API ---------- */
async function api(path, { method = 'GET', body } = {}) {
  const opts = { method, headers: {} };
  if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
  const res = await fetch(path, opts);
  let data = {};
  try { data = await res.json(); } catch { /* empty body */ }
  if (res.status === 401 && path !== '/api/login') {
    state.me = null;
    location.hash = '#/login';
    throw Object.assign(new Error(data.error || 'Please sign in.'), { status: 401, silent: true });
  }
  if (!res.ok) throw Object.assign(new Error(data.error || 'Something went wrong.'), { status: res.status, data });
  return data;
}

let toastTimer;
function toast(msg, kind = '') {
  const t = $('#toast');
  t.textContent = msg;
  t.className = `toast ${kind}`;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, 3200);
}

function paint(content, narrow = false) {
  app.className = narrow ? 'app narrow' : 'app';
  app.innerHTML = String(content);
}

/* ---------- dialogs ---------- */
let dialogSubmit = null;
function openDialog(content, onSubmit) {
  dialog.innerHTML = String(content);
  dialogSubmit = onSubmit;
  if (!dialog.open) dialog.showModal();
  const first = dialog.querySelector('input:not([type=hidden]):not([type=radio]):not([type=checkbox]), textarea, select');
  if (first && window.matchMedia('(min-width: 561px)').matches) first.focus();
}
function closeDialog() { if (dialog.open) dialog.close(); dialogSubmit = null; }
function dialogError(msg) {
  const box = dialog.querySelector('.error');
  if (box) { box.textContent = msg; box.hidden = false; box.scrollIntoView({ block: 'nearest' }); } else toast(msg, 'error');
}
dialog.addEventListener('submit', async (e) => {
  e.preventDefault();
  if (!dialogSubmit) return;
  const form = e.target;
  const data = Object.fromEntries(new FormData(form));
  const btn = form.querySelector('[type=submit]');
  if (btn) btn.disabled = true;
  try { await dialogSubmit(data, form, e.submitter); } catch (err) { if (!err.silent) dialogError(err.message); } finally { if (btn) btn.disabled = false; }
});
dialog.addEventListener('click', (e) => { if (e.target === dialog) closeDialog(); });

function confirmDialog({ title, body, confirm = 'Confirm', danger = false }) {
  return new Promise((resolve) => {
    openDialog(html`<form method="dialog">
      <h2>${title}</h2><div>${body}</div>
      <div class="dialog-actions"><button type="button" class="btn" data-action="close">Cancel</button>
      <button type="submit" class="btn ${danger ? 'danger solid' : 'primary'}">${confirm}</button></div></form>`,
    async () => { closeDialog(); resolve(true); });
    dialog.addEventListener('close', () => resolve(false), { once: true });
  });
}

/* ---------- router ---------- */
function parseHash() {
  const h = location.hash.slice(1) || '/';
  const [path, qs = ''] = h.split('?');
  return { path, q: Object.fromEntries(new URLSearchParams(qs)) };
}
function go(hash) { if (location.hash === hash) render(); else location.hash = hash; }
window.addEventListener('hashchange', render);

async function render() {
  closeNotif();
  if (dialog.open) closeDialog();
  const { path, q } = parseHash();
  try {
    if (!state.meta) state.meta = await api('/api/meta');
    if (path === '/login') return viewLogin();
    if (path === '/forgot') return viewForgot();
    if (path === '/set-password') return await viewSetPassword(q);
    if (!state.me) {
      const r = await api('/api/me');
      state.me = r.user; state.unread = r.unread;
    }
    if (state.me.must_change_password && path !== '/password') return go('#/password');
    renderTopbar(path);
    const staff = isStaff();
    let m;
    if (path === '/password') return viewPassword();
    if (staff) {
      if (path === '/staff') return await viewOverview(q);
      if ((m = path.match(/^\/staff\/report\/(\d+)\/(\d+)\/(\d{4}-\d{2})$/))) return await viewReport(+m[1], +m[2], m[3]);
      if (path === '/staff/students') return await viewStudents();
      if ((m = path.match(/^\/staff\/students\/(\d+)$/))) return await viewStudent(+m[1]);
      if (path === '/staff/tutors') return await viewTutors();
      if (path === '/staff/reminders') return await viewReminders();
      if (path === '/staff/activity') return await viewActivity();
      return go('#/staff');
    }
    if (path === '/tutor') return await viewTutorHome(q);
    if ((m = path.match(/^\/tutor\/student\/(\d+)$/))) return await viewReport(state.me.id, +m[1], q.month || thisMonth());
    return go('#/tutor');
  } catch (err) {
    if (err.silent) return;
    paint(html`<div class="banner alert">${icon('alert')}<div><b>Couldn't load this page</b><p>${err.message}</p>
      <p><a href="#/">Go back to the start</a></p></div></div>`, true);
  }
}

/* ---------- top bar & notifications ---------- */
function renderTopbar(path) {
  topbar.hidden = false;
  const staff = isStaff();
  const nav = [['/staff', 'Monthly reports'], ['/staff/students', 'Students'], ['/staff/tutors', 'Tutors & accounts'],
    ['/staff/reminders', 'Reminders'], ['/staff/activity', 'Activity log']];
  const active = (p) => path === p || (p === '/staff' && path.startsWith('/staff/report')) || (p === '/staff/students' && path.startsWith('/staff/students/'));
  topbar.innerHTML = String(html`<div class="topbar-inner">
    <a class="brand" href="#/"><img src="/favicon.svg" alt=""><span>LVAEP Tutor Hours<small>Literacy Volunteers · Essex &amp; Passaic</small></span></a>
    <span class="spacer"></span>
    <div class="user-chip"><b>${state.me.name}</b>${staff ? 'Staff' : 'Tutor'}</div>
    <button class="icon-btn" data-action="notif" aria-label="Notifications${state.unread ? ` (${state.unread} unread)` : ''}">${icon('bell')}${state.unread ? html`<span class="badge">${state.unread}</span>` : ''}</button>
    <a class="icon-btn" href="#/password" aria-label="Change password" title="Change password"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg></a>
    <button class="icon-btn" data-action="logout" aria-label="Sign out" title="Sign out">${icon('logout')}</button>
  </div>
  ${staff ? html`<div class="subnav"><nav class="topnav" aria-label="Staff">${nav.map(([p, label]) => html`<a href="#${p}" ${active(p) ? raw('aria-current="page"') : ''}>${label}</a>`)}</nav></div>` : ''}`);
}

function closeNotif() { const p = $('.notif-panel'); if (p) p.remove(); }
async function toggleNotif() {
  if ($('.notif-panel')) return closeNotif();
  const { items } = await api('/api/notifications');
  const panel = document.createElement('div');
  panel.className = 'notif-panel';
  panel.innerHTML = String(html`<header><b>Notifications</b><span class="spacer"></span><button class="btn ghost sm" data-action="notif">Close</button></header>
    ${items.length ? html`<ul>${items.map((n) => html`<li class="${n.read_at ? '' : 'unread'}">
      ${n.link ? html`<a href="${n.link}">${n.message}</a>` : n.message}<time>${fmtDT(n.created_at)}</time></li>`)}</ul>`
    : html`<div class="empty">No notifications yet.</div>`}`);
  topbar.appendChild(panel);
  if (state.unread) {
    await api('/api/notifications/read', { method: 'POST', body: {} });
    state.unread = 0;
    const badge = $('.topbar .badge');
    if (badge) badge.remove();
  }
}

/* ---------- login & password ---------- */
function viewLogin() {
  topbar.hidden = true;
  app.className = '';
  app.innerHTML = String(html`<div class="login-wrap"><div class="card login-card">
    <div class="brand"><img src="/favicon.svg" alt="" width="34" height="34"><span>LVAEP Tutor Hours<small>Literacy Volunteers of America — Essex &amp; Passaic Counties</small></span></div>
    <h1 style="margin-bottom:6px">Sign in</h1>
    <p class="muted" style="margin:0 0 18px">Log your tutoring sessions and submit your monthly hours.</p>
    <form id="login-form">
      <div class="error banner alert" hidden></div>
      <label class="field"><span>Email</span><input class="input" type="email" name="email" autocomplete="username" required></label>
      <label class="field"><span>Password</span><input class="input" type="password" name="password" autocomplete="current-password" required></label>
      <button class="btn primary block" type="submit">Sign in</button>
    </form>
    <p class="small" style="margin:14px 0 0"><a href="#/forgot">Forgot your password?</a></p>
    <div class="demo-accounts"><b>Prototype demo accounts</b> <span class="muted">(password <code>demo1234</code>, synthetic data)</span>
      <button type="button" data-action="demo" data-email="dana@lvaep.example"><span>Dana Whitfield</span><span class="muted">Staff</span></button>
      <button type="button" data-action="demo" data-email="maria@tutors.example"><span>Maria Santos</span><span class="muted">Tutor · 3 students</span></button>
      <button type="button" data-action="demo" data-email="james@tutors.example"><span>James Okoro</span><span class="muted">Tutor · 3 students</span></button>
    </div>
  </div></div>`);
  $('#login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.target));
    try {
      const r = await api('/api/login', { method: 'POST', body: data });
      state.me = r.user;
      const me = await api('/api/me');
      state.unread = me.unread;
      go(r.user.must_change_password ? '#/password' : '#/');
    } catch (err) {
      const box = $('#login-form .error');
      box.textContent = err.message; box.hidden = false;
    }
  });
}

function authCard(content) {
  topbar.hidden = true;
  app.className = '';
  app.innerHTML = String(html`<div class="login-wrap"><div class="card login-card">
    <div class="brand"><img src="/favicon.svg" alt="" width="34" height="34"><span>LVAEP Tutor Hours<small>Literacy Volunteers of America — Essex &amp; Passaic Counties</small></span></div>
    ${content}</div></div>`);
}

function viewForgot() {
  authCard(html`<h1 style="margin-bottom:6px">Forgot your password?</h1>
    <p class="muted" style="margin:0 0 18px">Enter the email you use for LVAEP Tutor Hours and we'll email you a link to choose a new password.</p>
    <form id="forgot-form">
      <div class="error banner alert" hidden></div>
      <label class="field"><span>Email</span><input class="input" type="email" name="email" autocomplete="username" required></label>
      <button class="btn primary block" type="submit">Email me a link</button>
    </form>
    <p class="small" style="margin:14px 0 0"><a href="#/login">‹ Back to sign in</a></p>`);
  $('#forgot-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const { email } = Object.fromEntries(new FormData(e.target));
    try {
      await api('/api/password/forgot', { method: 'POST', body: { email } });
      authCard(html`<h1 style="margin-bottom:6px">Check your email</h1>
        <p>If <b>${email}</b> has an LVAEP Tutor Hours account, we've sent it a link to choose a new password. The link works for 24 hours.</p>
        <p class="small muted">Nothing arrived after a few minutes? Check your spam folder, or ask LVAEP staff to send you a new link.</p>
        <p class="small" style="margin:14px 0 0"><a href="#/login">‹ Back to sign in</a></p>`);
    } catch (err) {
      const box = $('#forgot-form .error');
      box.textContent = err.message; box.hidden = false;
    }
  });
}

async function viewSetPassword(q) {
  let info;
  try {
    info = await api(`/api/password/link?token=${encodeURIComponent(q.token || '')}`);
  } catch (err) {
    return authCard(html`<h1 style="margin-bottom:6px">This link doesn't work anymore</h1>
      <p>${err.message}</p>
      <div class="row"><a class="btn primary" href="#/forgot">Email me a new link</a><a class="btn ghost" href="#/login">Sign in</a></div>`);
  }
  const invite = info.purpose === 'invite';
  authCard(html`<h1 style="margin-bottom:6px">${invite ? `Welcome, ${info.name.split(' ')[0]}!` : 'Choose a new password'}</h1>
    <p class="muted" style="margin:0 0 18px">${invite ? 'Choose a password to finish setting up your LVAEP Tutor Hours account.' : 'Choose a new password for your account.'}
      You'll sign in with <b>${info.email}</b>.</p>
    <form id="set-pw-form">
      <div class="error banner alert" hidden></div>
      <input type="email" name="username" value="${info.email}" autocomplete="username" hidden>
      <label class="field"><span>New password <span class="hint">· at least 8 characters</span></span><input class="input" type="password" name="password" minlength="8" autocomplete="new-password" required></label>
      <label class="field"><span>Repeat new password</span><input class="input" type="password" name="repeat" minlength="8" autocomplete="new-password" required></label>
      <button class="btn primary block" type="submit">${invite ? 'Create my account' : 'Save new password'}</button>
    </form>`);
  $('#set-pw-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.target));
    const box = $('#set-pw-form .error');
    if (d.password !== d.repeat) { box.textContent = 'The passwords do not match.'; box.hidden = false; return; }
    try {
      const r = await api('/api/password/link', { method: 'POST', body: { token: q.token, password: d.password } });
      state.me = r.user;
      const me = await api('/api/me');
      state.unread = me.unread;
      toast(invite ? 'Your account is ready.' : 'Password saved.');
      go('#/');
    } catch (err) { box.textContent = err.message; box.hidden = false; }
  });
}

function viewPassword() {
  const forced = state.me.must_change_password;
  paint(html`<div class="card card-pad" style="max-width:480px;margin:20px auto">
    <h1 style="margin-bottom:8px">${forced ? 'Choose your password' : 'Change password'}</h1>
    ${forced ? html`<p class="muted">Welcome, ${state.me.name}! You signed in with a temporary password from LVAEP staff. Please choose your own to continue.</p>` : ''}
    <form id="pw-form">
      <div class="error banner alert" hidden></div>
      <label class="field"><span>${forced ? 'Temporary password' : 'Current password'}</span><input class="input" type="password" name="current" autocomplete="current-password" required></label>
      <label class="field"><span>New password <span class="hint">· at least 8 characters</span></span><input class="input" type="password" name="new" minlength="8" autocomplete="new-password" required></label>
      <label class="field"><span>Repeat new password</span><input class="input" type="password" name="repeat" minlength="8" autocomplete="new-password" required></label>
      <div class="row"><button class="btn primary" type="submit">Save password</button>${forced ? '' : html`<a class="btn ghost" href="#/">Cancel</a>`}</div>
    </form></div>`, true);
  $('#pw-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.target));
    const box = $('#pw-form .error');
    if (d.new !== d.repeat) { box.textContent = 'The new passwords do not match.'; box.hidden = false; return; }
    try {
      await api('/api/me/password', { method: 'POST', body: { current: d.current, new: d.new } });
      state.me.must_change_password = 0;
      toast('Password saved.');
      go('#/');
    } catch (err) { box.textContent = err.message; box.hidden = false; }
  });
}

/* ---------- shared bits ---------- */
function monthSwitch(month, hrefFor) {
  const next = shiftMonth(month, 1);
  const future = next > thisMonth();
  return html`<nav class="month-switch" aria-label="Month">
    <a href="${hrefFor(shiftMonth(month, -1))}" aria-label="Previous month">‹</a>
    <strong>${monthLabel(month)}</strong>
    <a href="${hrefFor(next)}" aria-label="Next month" ${future ? raw('aria-disabled="true" tabindex="-1"') : ''}>›</a></nav>`;
}

function hoursBar(totals, target) {
  const scale = Math.max(target, totals.total, 1);
  return html`<div class="progress" role="img" aria-label="${fmtH(totals.total)} of about ${fmtH(target)} target hours">
    <i class="t" style="width:${(totals.tutoring / scale) * 100}%"></i><i class="h" style="width:${(totals.homework / scale) * 100}%"></i></div>`;
}

/* ---------- tutor home ---------- */
async function viewTutorHome(q) {
  const month = q.month || thisMonth();
  const d = await api(`/api/tutor/home?month=${month}`);
  const open = d.students.filter((s) => ['not_started', 'in_progress', 'returned'].includes(s.status));
  const banners = [];
  for (const o of d.overdue) {
    banners.push(html`<div class="banner alert">${icon('alert')}<div><b>Your ${o.label} hours are overdue</b>
      <p>Please submit the month for ${o.students.join(', ')}.${o.month !== month ? html` <a href="#/tutor?month=${o.month}">Go to ${monthShort(o.month)} →</a>` : ''}</p></div></div>`);
  }
  for (const s of d.students.filter((x) => x.status === 'returned')) {
    banners.push(html`<div class="banner warn">${icon('alert')}<div><b>Staff asked for a change to ${s.student_name}'s report</b>
      <p>“${s.staff_note}” <a href="#/tutor/student/${s.student_id}?month=${month}">Fix it →</a></p></div></div>`);
  }
  if (d.is_current && open.length && d.days_left <= 3) {
    banners.push(html`<div class="banner info">${icon('clock')}<div><b>${d.days_left === 0 ? `It's the last day of ${monthShort(month)}` : `${d.days_left} day${d.days_left === 1 ? '' : 's'} left in ${monthShort(month)}`}</b>
      <p>After your last session, review and submit the month for each student.</p></div></div>`);
  }
  if (d.students.length && !open.length) {
    banners.push(html`<div class="banner ok">${icon('check')}<div><b>All done for ${monthShort(month)}</b><p>Every report for this month has been submitted. Thank you!</p></div></div>`);
  }

  paint(html`
    <div class="page-head">
      <div><p class="muted" style="margin:0">Hi ${state.me.name.split(' ')[0]} 👋</p><h1>Your students</h1></div>
      <span class="spacer"></span>${monthSwitch(month, (m) => `#/tutor?month=${m}`)}
    </div>
    ${banners}
    ${d.students.length ? html`<div class="cards">${d.students.map((s) => studentCard(s, month))}</div>`
    : html`<div class="card empty"><b>No students assigned for ${monthLabel(month)}.</b><br>LVAEP staff will assign students after your training is complete.</div>`}
    <p class="small muted" style="margin-top:20px">Students do about ${fmtH(state.meta.weekly_target)} hours a week: 2 hours of tutoring and 2 hours of homework. Log each session after you meet, or all at once at the end of the month.</p>
  `);
}

function studentCard(s, month) {
  const locked = ['submitted', 'reviewed'].includes(s.status);
  const ended = s.end_date && s.end_date < today();
  return html`<article class="card student-card">
    <header><div><h3>${s.student_name}</h3><div class="muted small">${s.program}${s.co_tutors.length ? ` · also with ${s.co_tutors.join(', ')}` : ''}</div></div>
      <span class="spacer"></span>${chip(s.status)}</header>
    <div class="meta">
      <div>${icon('cal')}<span>${s.schedule || 'Schedule not set'}</span></div>
      <div>${icon('pin')}<span>${s.meeting_place || 'Meeting place not set'}</span></div>
      ${s.student_status !== 'active' ? html`<div>${studentChip(s.student_status)}</div>` : ''}
      ${ended ? html`<div class="muted">Assignment ended ${fmtDate(s.end_date)}</div>` : ''}
    </div>
    <div>
      <div class="hours-line"><span><b>${fmtH(s.totals.total)} h</b> this month</span><span>target ≈ ${fmtH(s.target_hours)} h</span></div>
      ${hoursBar(s.totals, s.target_hours)}
      <div class="legend" style="margin-top:6px"><span class="t">Tutoring ${fmtH(s.totals.tutoring)}</span><span class="h">Homework ${fmtH(s.totals.homework)}</span><span>${s.totals.entries} ${s.totals.entries === 1 ? 'entry' : 'entries'}</span></div>
    </div>
    <div class="actions">
      ${locked || ended ? '' : html`<button class="btn primary" data-action="quick-log" data-student="${s.student_id}" data-month="${month}">${icon('plus')} Log session</button>`}
      <a class="btn" href="#/tutor/student/${s.student_id}?month=${month}">${locked ? 'View report' : 'Review & submit'}</a>
    </div>
  </article>`;
}

/* ---------- monthly report (tutor and staff) ---------- */
let currentBundle = null;

async function viewReport(tutorId, studentId, month) {
  const b = await api(`/api/reports/${tutorId}/${studentId}/${month}`);
  currentBundle = b;
  const staff = isStaff();
  const r = b.report;
  const canEdit = staff || !r.locked;
  const hrefFor = (m) => (staff ? `#/staff/report/${tutorId}/${studentId}/${m}` : `#/tutor/student/${studentId}?month=${m}`);
  const backHref = staff ? `#/staff?month=${month}` : `#/tutor?month=${month}`;
  const a = b.assignment || {};
  const isCurrent = month === thisMonth();

  const banners = [];
  if (r.status === 'returned') {
    banners.push(html`<div class="banner warn">${icon('alert')}<div><b>${staff ? 'Returned to the tutor' : 'Staff asked for a change'}</b><p>“${r.staff_note}”</p>
      ${staff ? '' : html`<p>Fix the entries below, then submit the month again.</p>`}</div></div>`);
  }
  if (r.status === 'submitted') {
    banners.push(html`<div class="banner info">${icon('check')}<div><b>Submitted ${fmtDT(r.submitted_at)}</b>
      <p>${staff ? 'Waiting for staff review. Edits you make are recorded in the activity log.' : 'Thank you! This month is locked. If something needs to change, contact LVAEP staff and they can reopen it.'}</p></div></div>`);
  }
  if (r.status === 'reviewed') {
    banners.push(html`<div class="banner ok">${icon('check')}<div><b>Reviewed by ${r.reviewed_by || 'staff'} · ${fmtDT(r.reviewed_at)}</b>
      <p>Submitted ${fmtDT(r.submitted_at)}.${staff ? ' Edits you make are recorded in the activity log.' : ''}</p></div></div>`);
  }
  if (!r.locked && isCurrent && !staff && b.sessions.length) {
    banners.push(html`<div class="banner info">${icon('clock')}<div><b>${monthShort(month)} isn't over yet</b><p>Keep logging sessions. Submit after your last session of the month (by ${fmtDate(monthEnd(month), { month: 'long', day: 'numeric' })}).</p></div></div>`);
  }

  const fyRows = b.fiscal.months.map((m) => html`<tr class="${m.future ? 'future' : m.month === month ? 'current' : ''}">
    <td>${monthLabel(m.month)}</td><td>${m.future ? '' : m.attended}</td><td>${m.future ? '' : fmtH(m.tutoring)}</td>
    <td>${m.future ? '' : fmtH(m.homework)}</td><td>${m.future ? '' : fmtH(m.total)}</td></tr>`);

  const achieved = new Set(r.achievements);
  const extras = r.achievements.filter((x) => !state.meta.achievements.includes(x));
  const dis = canEdit ? '' : raw('disabled');
  const t = b.totals;

  paint(html`
    <a class="back" href="${backHref}">‹ ${staff ? 'Monthly reports' : 'Your students'}</a>
    <div class="report-head">
      <div><h1>${b.student.name}${studentChip(b.student.status)}</h1>
        <div class="meta">${staff ? html`Tutor <b>${b.tutor.name}</b> · ` : ''}${b.student.program}${b.co_tutors.length ? ` · also tutored by ${b.co_tutors.join(', ')}` : ''}</div>
        <div class="meta">${icon('cal')} ${a.schedule || 'Schedule not set'} &nbsp;·&nbsp; ${a.meeting_place || 'Meeting place not set'}</div>
      </div>
      <span class="spacer"></span>
      <div class="row">${chip(r.status)} ${monthSwitch(month, hrefFor)}</div>
    </div>
    ${banners}
    <div class="tiles">
      <div class="card tile"><div class="label">Tutoring</div><div class="value">${fmtH(t.tutoring)}<small> h</small></div></div>
      <div class="card tile"><div class="label">Homework</div><div class="value">${fmtH(t.homework)}<small> h</small></div></div>
      <div class="card tile"><div class="label">Month total</div><div class="value">${fmtH(t.total)}<small> / ≈${fmtH(b.target_hours)} h</small></div></div>
      <div class="card tile"><div class="label">${b.fiscal.label} to date</div><div class="value">${fmtH(b.fiscal.totals.total)}<small> h</small></div></div>
    </div>

    <section class="card">
      <div class="row card-pad" style="padding-bottom:8px"><h2>Sessions in ${monthShort(month)}</h2><span class="spacer"></span>
        ${canEdit ? html`<button class="btn primary sm" data-action="add-session">${icon('plus')} Log session</button>` : ''}</div>
      ${b.sessions.length ? html`<ul class="session-list">${b.sessions.map((s) => sessionRow(s, canEdit))}</ul>`
    : html`<div class="empty">No sessions logged for ${monthShort(month)} yet.${canEdit ? html`<br><button class="btn primary" style="margin-top:12px" data-action="add-session">${icon('plus')} Log your first session</button>` : ''}</div>`}
    </section>

    <form id="report-form" class="stack" style="margin-top:16px">
      <details class="card panel" ${r.achievements.length || r.achievement_notes ? raw('open') : ''}>
        <summary>Achievements this month <span class="muted small" style="font-weight:400">${r.achievements.length ? `· ${r.achievements.length} selected` : '· optional'}</span><span class="spacer"></span><span class="small muted save-state" aria-live="polite"></span></summary>
        <div class="panel-body">
          <p class="small muted" style="margin-top:0">Check anything the student accomplished this month. <i>(Placeholder list — the final fields will match LVAEP's form.)</i></p>
          ${state.meta.achievements.map((x) => html`<label class="check"><input type="checkbox" name="achievement" value="${x}" ${achieved.has(x) ? raw('checked') : ''} ${dis}><span>${x}</span></label>`)}
          ${extras.map((x) => html`<label class="check"><input type="checkbox" name="achievement" value="${x}" checked ${dis}><span>${x}</span></label>`)}
          <label class="field" style="margin-top:10px"><span>Notes on progress <span class="hint">· optional</span></span>
            <textarea class="input" name="achievement_notes" rows="3" ${dis} placeholder="e.g. Read her first full chapter book">${r.achievement_notes}</textarea></label>
        </div>
      </details>
      <details class="card panel" ${r.leaving_date || r.leaving_reason ? raw('open') : ''}>
        <summary>Did the student stop coming? <span class="muted small" style="font-weight:400">${r.leaving_date || r.leaving_reason ? '· reported' : '· only if it applies'}</span></summary>
        <div class="panel-body">
          <p class="small muted" style="margin-top:0">Tell staff the date of the last session and why. Staff decide whether the student is paused or dropped.</p>
          <div class="grid-2">
            <label class="field"><span>Date left</span><input class="input" type="date" name="leaving_date" value="${r.leaving_date || ''}" max="${today()}" ${dis}></label>
            <label class="field"><span>Reason</span><input class="input" name="leaving_reason" value="${r.leaving_reason}" maxlength="500" placeholder="e.g. Moved, new job schedule" ${dis}></label>
          </div>
        </div>
      </details>
      <details class="card panel">
        <summary>${b.fiscal.label} hours — month by month</summary>
        <div class="panel-body table-wrap"><table class="fy-table num">
          <thead><tr><th>Month</th><th>Sessions</th><th>Tutoring</th><th>Homework</th><th>Total</th></tr></thead>
          <tbody>${fyRows}</tbody>
          <tfoot><tr><td>Year to date</td><td>${b.fiscal.totals.attended}</td><td>${fmtH(b.fiscal.totals.tutoring)}</td><td>${fmtH(b.fiscal.totals.homework)}</td><td>${fmtH(b.fiscal.totals.total)}</td></tr></tfoot>
        </table></div>
      </details>
    </form>

    <div class="submit-bar">
      <div class="summary"><b>${monthLabel(month)}</b> · ${t.attended} session${t.attended === 1 ? '' : 's'} attended · <b>${fmtH(t.total)} h</b> (${fmtH(t.tutoring)} tutoring + ${fmtH(t.homework)} homework)</div>
      <a class="btn" href="/print?month=${month}&tutor=${tutorId}&student=${studentId}" target="_blank" rel="noopener">${icon('print')} ${staff ? 'Form / PDF' : 'Print copy'}</a>
      ${reportActions(b, staff)}
    </div>
  `, true);

  if (canEdit) {
    const form = $('#report-form');
    form.addEventListener('change', () => saveReportForm(form));
  }
}

function reportActions(b, staff) {
  const s = b.report.status;
  if (!staff) {
    if (b.report.locked) return '';
    return html`<button class="btn primary" data-action="submit-report">${icon('send')} Submit ${monthShort(b.month)}</button>`;
  }
  if (s === 'submitted') return html`<button class="btn" data-action="return-report">Return to tutor</button><button class="btn primary" data-action="review-report">${icon('check')} Mark reviewed</button>`;
  if (s === 'reviewed') return html`<button class="btn" data-action="return-report">Reopen / return</button>`;
  return html`<button class="btn" data-action="remind-one">${icon('send')} Remind tutor</button><button class="btn primary" data-action="submit-report">Submit for tutor</button>`;
}

function sessionRow(s, canEdit) {
  const present = s.attendance === 'present';
  const d = parseD(s.date);
  return html`<li>
    <div class="session-date"><span>${d.toLocaleDateString('en-US', { weekday: 'short' })}</span><b>${d.getDate()}</b></div>
    <div class="session-body"><div>${present ? 'Session' : html`<span class="chip neutral">${state.meta.attendance[s.attendance]}</span>`}</div>
      ${s.note ? html`<div class="note" title="${s.note}">${s.note}</div>` : ''}</div>
    <div class="session-hours">${present ? html`<b>${fmtH(s.tutoring_hours + s.homework_hours)} h</b><div>${fmtH(s.tutoring_hours)} tut · ${fmtH(s.homework_hours)} hw</div>` : html`<span class="muted">—</span>`}</div>
    ${canEdit ? html`<button class="btn ghost sm" data-action="edit-session" data-id="${s.id}" aria-label="Edit session on ${fmtDate(s.date)}">Edit</button>` : ''}
  </li>`;
}

let saveTimer;
function saveReportForm(form) {
  clearTimeout(saveTimer);
  const label = form.querySelector('.save-state');
  if (label) label.textContent = 'Saving…';
  saveTimer = setTimeout(async () => {
    const b = currentBundle;
    const fd = new FormData(form);
    try {
      await api(`/api/reports/${b.tutor.id}/${b.student.id}/${b.month}`, {
        method: 'PUT',
        body: { achievements: fd.getAll('achievement'), achievement_notes: fd.get('achievement_notes'),
          leaving_date: fd.get('leaving_date'), leaving_reason: fd.get('leaving_reason') },
      });
      if (label) label.textContent = 'Saved ✓';
    } catch (err) { if (label) label.textContent = ''; toast(err.message, 'error'); }
  }, 400);
}

function suggestDate(b) {
  const first = `${b.month}-01`;
  let min = first;
  if (b.assignment && b.assignment.start_date > min) min = b.assignment.start_date;
  let max = monthEnd(b.month);
  if (today() < max) max = today();
  if (b.assignment && b.assignment.end_date && b.assignment.end_date < max) max = b.assignment.end_date;
  const taken = new Set(b.sessions.map((s) => s.date));
  let candidate = max;
  if (b.sessions.length) {
    const d = parseD(b.sessions[b.sessions.length - 1].date);
    d.setDate(d.getDate() + 7);
    if (isoD(d) <= max) candidate = isoD(d);
  }
  if (taken.has(candidate)) candidate = '';
  return { min, max, value: candidate };
}

function sessionDialog(b, session) {
  const isNew = !session;
  const range = suggestDate(b);
  const s = session || { date: range.value, attendance: 'present', tutoring_hours: 2, homework_hours: 2, note: '' };
  const present = s.attendance === 'present';
  openDialog(html`<form>
    <h2>${isNew ? 'Log a session' : 'Edit session'} <span class="muted small" style="font-weight:400">· ${b.student.name}</span></h2>
    <div class="error" hidden></div>
    <label class="field"><span>Date</span><input class="input" type="date" name="date" value="${s.date}" min="${range.min}" max="${range.max}" required></label>
    <div class="field"><span>Attendance</span><div class="seg" role="radiogroup">
      ${Object.entries(state.meta.attendance).map(([k, v]) => html`<label><input type="radio" name="attendance" value="${k}" ${k === s.attendance ? raw('checked') : ''}><span>${v}</span></label>`)}
    </div></div>
    <div class="grid-2 hours-fields" ${present ? '' : raw('hidden')}>
      <div class="field"><span>Tutoring hours</span>${stepper('tutoring_hours', s.tutoring_hours)}</div>
      <div class="field"><span>Homework hours</span>${stepper('homework_hours', s.homework_hours)}</div>
    </div>
    <label class="field"><span>Note <span class="hint">· optional</span></span><input class="input" name="note" value="${s.note}" maxlength="500" placeholder="What did you work on?"></label>
    ${isStaff() ? html`<p class="small muted">You're editing ${b.tutor.name}'s report as staff — this change is recorded in the activity log.</p>` : ''}
    <div class="dialog-actions">
      ${isNew ? '' : html`<button type="button" class="btn danger" data-action="delete-session" data-id="${session.id}" style="margin-right:auto">Delete</button>`}
      <button type="button" class="btn" data-action="close">Cancel</button>
      <button type="submit" class="btn primary">${isNew ? 'Save session' : 'Save changes'}</button>
    </div></form>`, async (data) => {
    const body = { ...data, tutoring_hours: Number(data.tutoring_hours || 0), homework_hours: Number(data.homework_hours || 0) };
    if (isNew) await api('/api/sessions', { method: 'POST', body: { ...body, student_id: b.student.id, tutor_id: b.tutor.id } });
    else await api(`/api/sessions/${session.id}`, { method: 'PUT', body });
    closeDialog();
    toast(isNew ? 'Session saved.' : 'Session updated.');
    render();
  });
}

function stepper(name, value) {
  return html`<div class="stepper"><button type="button" data-action="step" data-name="${name}" data-delta="-0.5" aria-label="Less">−</button>
    <input type="number" name="${name}" value="${fmtH(value)}" min="0" max="8" step="0.25" inputmode="decimal" aria-label="${name.replace('_', ' ')}">
    <button type="button" data-action="step" data-name="${name}" data-delta="0.5" aria-label="More">+</button></div>`;
}

dialog.addEventListener('change', (e) => {
  if (e.target.name === 'attendance') {
    const fields = dialog.querySelector('.hours-fields');
    if (fields) fields.hidden = e.target.value !== 'present';
  }
});

/* ---------- staff: monthly overview ---------- */
async function viewOverview(q) {
  const month = q.month || thisMonth();
  const d = await api(`/api/staff/overview?month=${month}`);
  state.overview = d;
  if (q.status) state.ovFilter = q.status;
  const c = d.counts;
  const total = d.rows.length;
  const done = c.submitted + c.reviewed;
  const missingTutors = new Set(d.rows.filter((r) => !['submitted', 'reviewed'].includes(r.status)).map((r) => r.tutor_id)).size;
  const leaving = d.rows.filter((r) => r.leaving);
  const statOrder = ['not_started', 'in_progress', 'returned', 'submitted', 'reviewed'];
  const colors = { not_started: 'var(--s-not_started)', in_progress: 'var(--s-in_progress)', returned: 'var(--s-returned)', submitted: 'var(--s-submitted)', reviewed: 'var(--s-reviewed)' };

  paint(html`
    <div class="page-head">
      <div><h1>Monthly reports</h1><p class="muted" style="margin:2px 0 0">${d.fiscal_year} · ${total} tutor–student pairs · ${done} of ${total} submitted (${total ? Math.round((done / total) * 100) : 0}%) · ${fmtH(d.submitted_hours)} submitted hours</p></div>
      <span class="spacer"></span>${monthSwitch(month, (m) => `#/staff?month=${m}`)}
    </div>
    <div class="completion" aria-hidden="true" style="margin:-4px 0 16px">${statOrder.slice().reverse().map((s) => html`<i style="width:${total ? (c[s] / total) * 100 : 0}%;background:${colors[s]};opacity:.85"></i>`)}</div>
    ${leaving.length ? html`<div class="banner warn">${icon('alert')}<div><b>${leaving.length} report${leaving.length === 1 ? '' : 's'} say the student stopped coming</b>
      <p>${leaving.map((r, i) => html`${i ? ', ' : ''}<a href="#/staff/report/${r.tutor_id}/${r.student_id}/${month}">${r.student_name}</a>`)} — review their status on the Students page.</p></div></div>` : ''}
    <div class="stat-row">
      <button class="card stat" data-action="ov-filter" data-status="all" aria-pressed="${state.ovFilter === 'all'}"><div class="label">All pairs</div><div class="value">${total}</div></button>
      ${statOrder.map((s) => html`<button class="card stat" data-action="ov-filter" data-status="${s}" aria-pressed="${state.ovFilter === s}">
        <div class="label"><span class="dot" style="background:${colors[s]}"></span>${STATUS[s]}</div><div class="value">${c[s]}</div></button>`)}
    </div>
    <div class="toolbar">
      <input class="input" type="search" id="ov-search" placeholder="Search tutor or student" value="${state.ovSearch}" aria-label="Search tutor or student">
      <span class="spacer"></span>
      <button class="btn" data-action="remind-missing" data-month="${month}" ${missingTutors ? '' : raw('disabled')}>${icon('send')} Remind ${missingTutors} tutor${missingTutors === 1 ? '' : 's'}</button>
      <a class="btn" href="/print?month=${month}" target="_blank" rel="noopener">${icon('print')} Print submitted forms</a>
      <a class="btn" href="/export/summary.csv?month=${month}">${icon('download')} Summary CSV</a>
      <a class="btn" href="/export/sessions.csv?month=${month}">${icon('download')} Sessions CSV</a>
    </div>
    <div class="card table-wrap"><table class="data">
      <thead><tr><th>Tutor</th><th>Student</th><th>Status</th><th class="n">Sessions</th><th class="n">Tutoring</th><th class="n">Homework</th><th class="n">Total</th><th class="n">FY to date</th><th>Submitted</th></tr></thead>
      <tbody id="ov-body"></tbody>
    </table></div>
  `);
  renderOverviewRows();
  $('#ov-search').addEventListener('input', (e) => { state.ovSearch = e.target.value; renderOverviewRows(); });
}

function renderOverviewRows() {
  const d = state.overview;
  const term = state.ovSearch.trim().toLowerCase();
  const rows = d.rows.filter((r) => (state.ovFilter === 'all' || r.status === state.ovFilter)
    && (!term || r.tutor_name.toLowerCase().includes(term) || r.student_name.toLowerCase().includes(term)));
  $('#ov-body').innerHTML = rows.length ? String(html`${rows.map((r) => html`<tr class="clickable" data-href="#/staff/report/${r.tutor_id}/${r.student_id}/${d.month}" tabindex="0">
    <td><b>${r.tutor_name}</b><div class="sub">${r.schedule}</div></td>
    <td>${r.student_name}${studentChip(r.student_status)}${r.leaving ? html` <span class="flag" title="Tutor reports the student stopped coming">● left</span>` : ''}</td>
    <td>${chip(r.status)}</td>
    <td class="n">${r.totals.attended}${r.totals.entries > r.totals.attended ? html`<span class="sub"> / ${r.totals.entries}</span>` : ''}</td>
    <td class="n">${fmtH(r.totals.tutoring)}</td><td class="n">${fmtH(r.totals.homework)}</td><td class="n"><b>${fmtH(r.totals.total)}</b></td>
    <td class="n">${fmtH(r.fy_total)}</td>
    <td class="nowrap">${r.submitted_at ? fmtDT(r.submitted_at) : html`<span class="muted">—</span>`}</td></tr>`)}`)
    : String(html`<tr><td colspan="9" class="empty">No reports match.</td></tr>`);
  document.querySelectorAll('[data-action="ov-filter"]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.status === state.ovFilter)));
}

/* ---------- staff: students ---------- */
async function viewStudents() {
  const { items, fiscal_year } = await api('/api/staff/students');
  const counts = { active: 0, paused: 0, dropped: 0 };
  items.forEach((s) => { counts[s.status] += 1; });
  paint(html`
    <div class="page-head"><div><h1>Students</h1><p class="muted" style="margin:2px 0 0">${counts.active} active · ${counts.paused} paused · ${counts.dropped} dropped</p></div>
      <span class="spacer"></span><button class="btn primary" data-action="new-student">${icon('plus')} Add student</button></div>
    <div class="toolbar"><input class="input" type="search" id="st-search" placeholder="Search students or tutors" aria-label="Search students">
      <select class="input" id="st-status" style="max-width:180px" aria-label="Filter by status"><option value="">All statuses</option><option value="active">Active</option><option value="paused">Paused</option><option value="dropped">Dropped</option></select></div>
    <div class="card table-wrap"><table class="data">
      <thead><tr><th>Student</th><th>Status</th><th>Current tutor(s)</th><th class="n">${fiscal_year} hours</th><th>Last session</th></tr></thead>
      <tbody id="st-body">${items.map((s) => html`<tr class="clickable ${s.status === 'dropped' ? 'dim' : ''}" data-href="#/staff/students/${s.id}" tabindex="0"
        data-search="${`${s.first_name} ${s.last_name} ${s.tutors || ''}`.toLowerCase()}" data-status="${s.status}">
        <td><b>${s.first_name} ${s.last_name}</b><div class="sub">${s.program}</div></td>
        <td>${s.status === 'active' ? html`<span class="chip reviewed">Active</span>` : studentChip(s.status)}</td>
        <td>${s.tutors || html`<span class="flag">No tutor assigned</span>`}</td>
        <td class="n">${fmtH(s.fy_hours)}</td><td>${s.last_session ? fmtDate(s.last_session) : html`<span class="muted">—</span>`}</td></tr>`)}</tbody>
    </table></div>`);
  const filter = () => {
    const term = $('#st-search').value.trim().toLowerCase();
    const st = $('#st-status').value;
    document.querySelectorAll('#st-body tr').forEach((tr) => {
      tr.hidden = (term && !tr.dataset.search.includes(term)) || (st && tr.dataset.status !== st);
    });
  };
  $('#st-search').addEventListener('input', filter);
  $('#st-status').addEventListener('change', filter);
}

function studentForm(s = {}) {
  return html`<div class="error" hidden></div>
    <div class="grid-2">
      <label class="field"><span>First name</span><input class="input" name="first_name" value="${s.first_name || ''}" required></label>
      <label class="field"><span>Last name</span><input class="input" name="last_name" value="${s.last_name || ''}" required></label>
    </div>
    <div class="grid-2">
      <label class="field"><span>Program</span><select class="input" name="program">
        ${['ESL', 'Basic Literacy'].map((p) => html`<option ${s.program === p ? raw('selected') : ''}>${p}</option>`)}</select></label>
      ${s.id ? '' : html`<label class="field"><span>Enrolled on</span><input class="input" type="date" name="enrolled_on" value="${today()}"></label>`}
    </div>
    <label class="field"><span>Staff notes <span class="hint">· not shown to tutors</span></span><textarea class="input" name="notes" rows="2">${s.notes || ''}</textarea></label>`;
}

async function viewStudent(id) {
  const [d, tutors] = await Promise.all([api(`/api/staff/students/${id}`), api('/api/staff/tutors')]);
  const s = d.student;
  const open = d.assignments.filter((a) => !a.end_date);
  const past = d.assignments.filter((a) => a.end_date);
  const activeTutors = tutors.items.filter((t) => t.role === 'tutor' && t.active);
  paint(html`
    <a class="back" href="#/staff/students">‹ Students</a>
    <div class="report-head"><div><h1>${s.first_name} ${s.last_name}${s.status === 'active' ? html` <span class="chip reviewed">Active</span>` : studentChip(s.status)}</h1>
      <div class="meta">${s.program} · enrolled ${fmtDate(s.enrolled_on, { month: 'short', day: 'numeric', year: 'numeric' })}</div></div>
      <span class="spacer"></span>
      <div class="row">
        <button class="btn" data-action="edit-student">Edit details</button>
        ${s.status === 'active' ? html`<button class="btn" data-action="student-status" data-status="paused">Pause</button>` : ''}
        ${s.status === 'paused' ? html`<button class="btn" data-action="student-status" data-status="active">Resume</button>` : ''}
        ${s.status !== 'dropped' ? html`<button class="btn danger" data-action="drop-student">Drop student</button>` : html`<button class="btn" data-action="readmit-student">Readmit…</button>`}
      </div></div>
    ${s.status === 'dropped' ? html`<div class="banner alert">${icon('alert')}<div><b>Dropped on ${fmtDate(s.left_on, { month: 'long', day: 'numeric', year: 'numeric' })}</b><p>${s.leave_reason}. A drop is permanent — only staff can readmit the student.</p></div></div>` : ''}
    ${s.status === 'paused' ? html`<div class="banner info">${icon('clock')}<div><b>Paused</b><p>Tutors keep the student on their list; resume when they come back.</p></div></div>` : ''}
    ${s.notes ? html`<div class="card card-pad" style="margin-bottom:14px"><b>Staff notes</b><p style="margin:4px 0 0">${s.notes}</p></div>` : ''}

    <div class="section-title"><h2>Tutors</h2><span class="spacer"></span>${s.status !== 'dropped' ? html`<button class="btn primary sm" data-action="assign-tutor">${icon('plus')} Assign a tutor</button>` : ''}</div>
    <div class="card table-wrap"><table class="data">
      <thead><tr><th>Tutor</th><th>Days / times</th><th>Meeting place</th><th>From</th><th>To</th><th></th></tr></thead>
      <tbody>${open.concat(past).map((a) => html`<tr class="${a.end_date ? 'dim' : ''}"><td><b>${a.tutor_name}</b></td><td>${a.schedule}</td><td>${a.meeting_place}</td>
        <td class="nowrap">${fmtDate(a.start_date, { month: 'short', day: 'numeric', year: 'numeric' })}</td><td class="nowrap">${a.end_date ? fmtDate(a.end_date, { month: 'short', day: 'numeric', year: 'numeric' }) : 'Current'}</td>
        <td class="nowrap">${a.end_date ? '' : html`<button class="btn sm" data-action="edit-assignment" data-id="${a.id}">Edit</button> <button class="btn sm danger" data-action="end-assignment" data-id="${a.id}">End</button>`}</td></tr>`)}
      ${d.assignments.length ? '' : html`<tr><td colspan="6" class="empty">No tutor assigned yet.</td></tr>`}</tbody></table></div>

    <div class="section-title"><h2>${d.fiscal_year} monthly reports</h2></div>
    <div class="card table-wrap"><table class="data">
      <thead><tr><th>Month</th><th>Tutor</th><th>Status</th><th class="n">Sessions</th><th class="n">Tutoring</th><th class="n">Homework</th><th class="n">Total</th></tr></thead>
      <tbody>${d.history.map((h) => html`<tr class="clickable" data-href="#/staff/report/${h.tutor_id}/${s.id}/${h.month}" tabindex="0"><td>${h.month_label}</td><td>${h.tutor_name}</td><td>${chip(h.status)}</td>
        <td class="n">${h.totals.attended}</td><td class="n">${fmtH(h.totals.tutoring)}</td><td class="n">${fmtH(h.totals.homework)}</td><td class="n"><b>${fmtH(h.totals.total)}</b></td></tr>`)}
      ${d.history.length ? '' : html`<tr><td colspan="7" class="empty">No reports this fiscal year.</td></tr>`}</tbody></table></div>
  `);
  state.studentPage = { d, activeTutors };
}

function assignmentDialog(student, activeTutors, a) {
  const isNew = !a;
  openDialog(html`<form>
    <h2>${isNew ? `Assign a tutor to ${student.first_name}` : `Edit ${a.tutor_name} ↔ ${student.first_name}`}</h2>
    <div class="error" hidden></div>
    ${isNew ? html`<label class="field"><span>Tutor</span><select class="input" name="tutor_id" required><option value="">Choose a tutor…</option>
      ${activeTutors.map((t) => html`<option value="${t.id}">${t.name} — ${t.students} student${t.students === 1 ? '' : 's'}${t.training_hours < 10 ? ` · ${fmtH(t.training_hours)}/10 training h` : ''}</option>`)}</select></label>` : ''}
    <label class="field"><span>Days / times</span><input class="input" name="schedule" value="${a ? a.schedule : ''}" placeholder="e.g. Tuesdays, 6:00–8:00 pm"></label>
    <label class="field"><span>Meeting place</span><input class="input" name="meeting_place" value="${a ? a.meeting_place : ''}" placeholder="e.g. Paterson Free Public Library"></label>
    ${isNew ? html`<label class="field"><span>Start date</span><input class="input" type="date" name="start_date" value="${today()}" required></label>` : ''}
    <input type="hidden" name="confirm" value="">
    <div class="dialog-actions"><button type="button" class="btn" data-action="close">Cancel</button><button type="submit" class="btn primary">${isNew ? 'Assign tutor' : 'Save'}</button></div>
  </form>`, async (data, form) => {
    if (!isNew) {
      await api(`/api/staff/assignments/${a.id}`, { method: 'PUT', body: data });
    } else {
      try {
        await api('/api/staff/assignments', { method: 'POST', body: { ...data, student_id: student.id, confirm: !!data.confirm } });
      } catch (err) {
        if (err.data && err.data.needs_confirm) {
          dialogError(`${err.message} Press “Assign anyway” to continue.`);
          form.confirm.value = '1';
          form.querySelector('[type=submit]').textContent = 'Assign anyway';
          return;
        }
        throw err;
      }
    }
    closeDialog();
    toast(isNew ? 'Tutor assigned — they have been notified.' : 'Assignment updated.');
    render();
  });
}

/* ---------- staff: tutors & accounts ---------- */
async function viewTutors() {
  const { items } = await api('/api/staff/tutors');
  state.tutors = items;
  const tutors = items.filter((u) => u.role === 'tutor');
  paint(html`
    <div class="page-head"><div><h1>Tutors &amp; accounts</h1><p class="muted" style="margin:2px 0 0">${tutors.filter((t) => t.active).length} active tutors · ${items.filter((u) => u.role === 'staff').length} staff accounts</p></div>
      <span class="spacer"></span><button class="btn primary" data-action="new-account">${icon('plus')} Create account</button></div>
    <div class="card table-wrap"><table class="data">
      <thead><tr><th>Name</th><th>Role</th><th>Training</th><th class="n">Students</th><th>Last session</th><th>Status</th><th></th></tr></thead>
      <tbody>${items.map((u) => html`<tr class="${u.active ? '' : 'dim'}">
        <td><b>${u.name}</b><div class="sub">${u.email}${u.phone ? ` · ${u.phone}` : ''}</div></td>
        <td>${u.role === 'staff' ? 'Staff' : 'Tutor'}</td>
        <td>${u.role === 'tutor' ? (u.training_hours >= 10 ? html`<span class="chip reviewed">Trained</span>` : html`<span class="chip in_progress">${fmtH(u.training_hours)}/10 h</span>`) : ''}</td>
        <td class="n">${u.role === 'tutor' ? u.students : ''}</td>
        <td>${u.last_session ? fmtDate(u.last_session) : html`<span class="muted">—</span>`}</td>
        <td>${u.active ? (u.must_change_password ? html`<span class="chip neutral">Invite pending</span>` : 'Active') : 'Deactivated'}</td>
        <td><button class="btn sm" data-action="edit-account" data-id="${u.id}">Edit</button></td></tr>`)}</tbody>
    </table></div>
    <p class="small muted">Tutors are assigned students after completing 10 hours of training. New accounts get an email invitation to choose their password (a temporary password is shown too, as a backup).</p>`);
}

function accountDialog(u) {
  const isNew = !u;
  openDialog(html`<form>
    <h2>${isNew ? 'Create an account' : `Edit ${u.name}`}</h2>
    <div class="error" hidden></div>
    <label class="field"><span>Full name</span><input class="input" name="name" value="${u ? u.name : ''}" required></label>
    <div class="grid-2">
      <label class="field"><span>Email</span><input class="input" type="email" name="email" value="${u ? u.email : ''}" required></label>
      <label class="field"><span>Phone <span class="hint">· optional</span></span><input class="input" type="tel" name="phone" value="${u ? u.phone || '' : ''}"></label>
    </div>
    <div class="grid-2">
      ${isNew ? html`<label class="field"><span>Role</span><select class="input" name="role"><option value="tutor">Tutor</option><option value="staff">Staff</option></select></label>` : ''}
      <label class="field"><span>Training hours completed</span><input class="input" type="number" name="training_hours" min="0" step="0.5" value="${u ? u.training_hours : 0}"></label>
    </div>
    ${isNew ? '' : html`<label class="check"><input type="checkbox" name="active" value="1" ${u.active ? raw('checked') : ''}><span>Account is active <span class="muted small">— uncheck to block sign-in (history is kept)</span></span></label>`}
    <div class="dialog-actions">
      ${isNew ? '' : html`<button type="button" class="btn" data-action="send-link" data-id="${u.id}" style="margin-right:auto" title="Email them a link to ${u.must_change_password ? 'accept their invitation' : 'choose a new password'}">${icon('send')} Email sign-in link</button>
        <button type="button" class="btn ghost" data-action="reset-password" data-id="${u.id}">Temporary password</button>`}
      <button type="button" class="btn" data-action="close">Cancel</button>
      <button type="submit" class="btn primary">${isNew ? 'Create account' : 'Save'}</button>
    </div></form>`, async (data) => {
    if (isNew) {
      const r = await api('/api/staff/tutors', { method: 'POST', body: data });
      showTempPassword(data.name, data.email, r.temp_password, true, r.email);
    } else {
      await api(`/api/staff/tutors/${u.id}`, { method: 'PUT', body: { ...data, active: !!data.active } });
      closeDialog();
      toast('Account updated.');
      render();
    }
  });
}

function emailNote(status) {
  if (!status) return '';
  if (status.mode === 'resend') return status.redirect_to ? ` (test mode: it actually goes to ${status.redirect_to})` : '';
  if (status.mode === 'outbox') return ' — email isn\'t connected yet, so it was saved on the server instead of sent';
  return ' — email is turned off, so it was not sent';
}

function showTempPassword(name, email, pw, created, status) {
  const emailed = created && status && status.mode === 'resend';
  openDialog(html`<div class="dialog-inner">
    <h2>${created ? 'Account created' : 'Temporary password'}</h2>
    ${created ? html`<p>We emailed <b>${name}</b> an invitation at <b>${email}</b> to choose their password${emailNote(status)}.</p>` : ''}
    ${emailed ? html`<details><summary class="small">Show a temporary password instead (if the email doesn't arrive)</summary>` : ''}
    <p${emailed ? '' : raw(' style="margin-top:0"')}>${created ? 'Or give' : 'Give'} <b>${name}</b> these sign-in details. They'll choose their own password when they first sign in.</p>
    <dl class="kv"><dt>Sign-in page</dt><dd>${location.origin}</dd><dt>Email</dt><dd>${email}</dd></dl>
    <p class="small muted" style="margin-bottom:6px">Temporary password (shown once):</p>
    <div class="temp-pw">${pw}</div>
    ${emailed ? raw('</details>') : ''}
    <div class="dialog-actions"><button type="button" class="btn primary" data-action="close-render">Done</button></div></div>`);
}

/* ---------- staff: reminders ---------- */
const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const EMAIL_KIND = { invite: 'Invitation', reset: 'Password reset', month_end: 'Month-end reminder', overdue: 'Overdue reminder',
  manual: 'Reminder from staff', weekly: 'Weekly nudge', returned: 'Report returned', assigned: 'New student', leaving: 'Student stopped',
  calendar: 'Schedule update' };
const EMAIL_STATUS = { queued: 'Waiting to send', sent: 'Sent', saved: 'Saved (not sent)', failed: 'Failed — will retry', skipped: 'Skipped' };
function emailBanner(st) {
  if (st.mode === 'resend') {
    return html`<div class="banner info">${icon('send')}<div><b>Emails are on.</b><p>Reminders and other notifications are emailed from <b>${st.from}</b> as well as shown in the notification bell.${st.redirect_to ? html` <b>Test mode:</b> every email currently goes to ${st.redirect_to}.` : ''}</p></div></div>`;
  }
  if (st.mode === 'outbox') {
    return html`<div class="banner info">${icon('bell')}<div><b>Email isn't connected yet.</b><p>Reminders appear in each tutor's notification bell. Emails are saved on the server for previewing instead of being sent — add a Resend API key to send them (see the README).</p></div></div>`;
  }
  return html`<div class="banner info">${icon('bell')}<div><b>Email is turned off.</b><p>Reminders appear in each tutor's notification bell only.</p></div></div>`;
}

async function viewReminders() {
  const [d, mail] = await Promise.all([api('/api/staff/reminders'), api('/api/staff/emails')]);
  const s = d.settings;
  const cur = thisMonth();
  const prev = shiftMonth(cur, -1);
  const KIND = { month_end: 'Last day of month', overdue: 'Overdue (3rd of month)', weekly: 'Weekly nudge', manual: 'Sent by staff' };
  paint(html`
    <div class="page-head"><div><h1>Reminders</h1><p class="muted" style="margin:2px 0 0">So staff don't have to chase tutors for their hours.</p></div></div>
    ${emailBanner(mail.status)}
    <div class="cards" style="grid-template-columns:repeat(auto-fit,minmax(320px,1fr))">
      <section class="card card-pad"><h2>Automatic reminders</h2>
        <form id="rem-form">
          <label class="switch"><input type="checkbox" name="reminder_month_end" ${s.reminder_month_end === '1' ? raw('checked') : ''}><span><b>Last day of the month</b><br><span class="small muted">“It's the last day of October — don't forget to submit your hours.” Sent to tutors who haven't submitted.</span></span></label>
          <label class="switch"><input type="checkbox" name="reminder_overdue" ${s.reminder_overdue === '1' ? raw('checked') : ''}><span><b>Overdue follow-up</b><br><span class="small muted">On the 3rd, tutors who still haven't submitted last month get a second reminder.</span></span></label>
          <label class="switch"><input type="checkbox" name="reminder_weekly" ${s.reminder_weekly === '1' ? raw('checked') : ''}><span><b>Weekly nudge</b><br><span class="small muted">Tutors who logged nothing in the past 7 days get a reminder on
            <select class="input" name="reminder_weekly_day" style="display:inline-block;width:auto;min-height:32px;padding:2px 8px">${WEEKDAYS.map((w, i) => html`<option value="${i}" ${String(i) === s.reminder_weekly_day ? raw('selected') : ''}>${w}</option>`)}</select>.</span></span></label>
          <label class="switch"><input type="checkbox" name="email_notifications" ${s.email_notifications !== '0' ? raw('checked') : ''}><span><b>Also send notifications by email</b><br><span class="small muted">Reminders, returned reports, new students and schedule changes are emailed too. Invitations and password links are always emailed.</span></span></label>
        </form>
        <button class="btn sm" data-action="run-reminders" style="margin-top:6px">Run today's check now</button>
      </section>
      <section class="card card-pad"><h2>Send a reminder now</h2>
        <p class="small muted" style="margin-top:4px">Notifies every tutor with an unsubmitted report for the month.</p>
        <div class="row"><button class="btn primary" data-action="remind-missing" data-month="${prev}">${icon('send')} ${monthShort(prev)} reports</button>
          <button class="btn" data-action="remind-missing" data-month="${cur}">${icon('send')} ${monthShort(cur)} reports</button></div>
      </section>
    </div>
    <div class="section-title"><h2>Reminder history</h2></div>
    <div class="card table-wrap"><table class="data"><thead><tr><th>When</th><th>Type</th><th>For</th><th class="n">Tutors notified</th><th>By</th></tr></thead>
      <tbody>${d.runs.map((r) => html`<tr><td class="nowrap">${fmtDT(r.ran_at)}</td><td>${KIND[r.kind] || r.kind}</td><td>${r.kind === 'weekly' ? r.period_key : monthLabel(r.period_key)}</td><td class="n">${r.recipients}</td><td>${r.triggered_by_name || 'Automatic'}</td></tr>`)}
      ${d.runs.length ? '' : html`<tr><td colspan="5" class="empty">No reminders sent yet.</td></tr>`}</tbody></table></div>
    <div class="section-title"><h2>Recent emails</h2></div>
    <div class="card table-wrap"><table class="data"><thead><tr><th>When</th><th>To</th><th>Email</th><th>Status</th></tr></thead>
      <tbody>${mail.items.map((m) => html`<tr><td class="nowrap">${fmtDT(m.created_at)}</td><td>${m.to_name}<div class="sub">${m.to_email}</div></td>
        <td>${EMAIL_KIND[m.kind] || m.kind}<div class="sub">${m.subject}</div></td>
        <td>${EMAIL_STATUS[m.status] || m.status}${m.status === 'failed' || m.status === 'skipped' ? html`<div class="sub">${m.last_error}</div>` : ''}</td></tr>`)}
      ${mail.items.length ? '' : html`<tr><td colspan="4" class="empty">No emails yet.</td></tr>`}</tbody></table></div>`);
  $('#rem-form').addEventListener('change', async (e) => {
    const f = e.currentTarget;
    await api('/api/staff/reminders/settings', { method: 'PUT', body: {
      reminder_month_end: f.reminder_month_end.checked ? '1' : '0', reminder_overdue: f.reminder_overdue.checked ? '1' : '0',
      reminder_weekly: f.reminder_weekly.checked ? '1' : '0', reminder_weekly_day: f.reminder_weekly_day.value,
      email_notifications: f.email_notifications.checked ? '1' : '0' } });
    toast('Reminder settings saved.');
  });
}

/* ---------- staff: activity ---------- */
async function viewActivity() {
  const { items } = await api('/api/staff/activity');
  paint(html`<div class="page-head"><div><h1>Activity log</h1><p class="muted" style="margin:2px 0 0">Every staff change, correction, submission and drop — newest first.</p></div></div>
    <div class="card table-wrap"><table class="data"><thead><tr><th>When</th><th>Who</th><th>Action</th><th>Details</th></tr></thead>
    <tbody>${items.map((a) => html`<tr><td class="nowrap">${fmtDT(a.created_at)}</td><td class="nowrap">${a.user_name || '—'}</td><td class="nowrap"><code>${a.action}</code></td><td>${a.detail}</td></tr>`)}</tbody></table></div>`);
}

/* ---------- global click actions ---------- */
const actions = {
  close: () => closeDialog(),
  'close-render': () => { closeDialog(); render(); },
  notif: () => toggleNotif(),
  async logout() { await api('/api/logout', { method: 'POST', body: {} }).catch(() => {}); state.me = null; go('#/login'); },
  demo(el) { const f = $('#login-form'); f.email.value = el.dataset.email; f.password.value = 'demo1234'; f.requestSubmit(); },
  step(el) {
    const input = el.parentElement.querySelector('input');
    const v = Math.min(8, Math.max(0, (Number(input.value) || 0) + Number(el.dataset.delta)));
    input.value = fmtH(v);
  },
  async 'quick-log'(el) {
    const b = await api(`/api/reports/${state.me.id}/${el.dataset.student}/${el.dataset.month}`);
    currentBundle = b;
    sessionDialog(b);
  },
  'add-session': () => sessionDialog(currentBundle),
  'edit-session': (el) => sessionDialog(currentBundle, currentBundle.sessions.find((s) => s.id === Number(el.dataset.id))),
  async 'delete-session'(el) {
    const b = currentBundle;
    const s = b.sessions.find((x) => x.id === Number(el.dataset.id));
    if (!(await confirmDialog({ title: 'Delete this session?', body: html`<p>${fmtDate(s.date, { weekday: 'long', month: 'long', day: 'numeric' })} — this can't be undone.</p>`, confirm: 'Delete', danger: true }))) return;
    await api(`/api/sessions/${s.id}`, { method: 'DELETE' });
    toast('Session deleted.');
    render();
  },
  async 'submit-report'() {
    const b = currentBundle;
    const t = b.totals;
    const early = !b.month_closed;
    const ok = await confirmDialog({
      title: `Submit ${monthLabel(b.month)}?`,
      body: html`<p><b>${b.student.name}</b>${isStaff() ? html` · tutor ${b.tutor.name}` : ''}</p>
        <dl class="kv"><dt>Sessions attended</dt><dd>${t.attended} of ${t.entries} entries</dd><dt>Tutoring</dt><dd>${fmtH(t.tutoring)} h</dd><dt>Homework</dt><dd>${fmtH(t.homework)} h</dd><dt>Total</dt><dd><b>${fmtH(t.total)} h</b></dd>
        <dt>Achievements</dt><dd>${b.report.achievements.length || 'None'}</dd></dl>
        ${early ? html`<div class="banner warn" style="margin-top:14px">${icon('clock')}<div><b>${monthShort(b.month)} isn't over yet.</b><p>Only submit now if this was your last session of the month.</p></div></div>` : ''}
        <p class="small muted">After you submit, the month is locked. Staff can reopen it if something needs fixing.</p>`,
      confirm: isStaff() ? 'Submit for tutor' : 'Submit month',
    });
    if (!ok) return;
    try {
      await api(`/api/reports/${b.tutor.id}/${b.student.id}/${b.month}/submit`, { method: 'POST', body: {} });
      toast(isStaff() ? 'Submitted on the tutor\'s behalf.' : 'Submitted — thank you!');
      render();
    } catch (err) { toast(err.message, 'error'); }
  },
  async 'review-report'() {
    const b = currentBundle;
    await api(`/api/reports/${b.tutor.id}/${b.student.id}/${b.month}/review`, { method: 'POST', body: {} });
    toast('Marked as reviewed.');
    render();
  },
  'return-report'() {
    const b = currentBundle;
    openDialog(html`<form><h2>Return to ${b.tutor.name}</h2><div class="error" hidden></div>
      <p class="small muted" style="margin-top:0">The report is unlocked so the tutor can fix it, and they get a notification with your note.</p>
      <label class="field"><span>What needs to change?</span><textarea class="input" name="note" rows="3" required placeholder="e.g. The Oct 6 session shows 4 h tutoring — should it be 2 + 2?"></textarea></label>
      <div class="dialog-actions"><button type="button" class="btn" data-action="close">Cancel</button><button type="submit" class="btn primary">Return report</button></div></form>`,
    async (data) => {
      await api(`/api/reports/${b.tutor.id}/${b.student.id}/${b.month}/return`, { method: 'POST', body: data });
      closeDialog(); toast('Returned to the tutor.'); render();
    });
  },
  async 'remind-one'() {
    const b = currentBundle;
    await api('/api/staff/reminders/send', { method: 'POST', body: { month: b.month } });
    toast(`Reminder sent to every tutor missing ${monthShort(b.month)}.`);
  },
  async 'remind-missing'(el) {
    const month = el.dataset.month;
    const ok = await confirmDialog({ title: `Send ${monthShort(month)} reminders?`, body: html`<p>Every tutor with an unsubmitted ${monthLabel(month)} report will get a reminder listing the students they still need to submit.</p>`, confirm: 'Send reminders' });
    if (!ok) return;
    const r = await api('/api/staff/reminders/send', { method: 'POST', body: { month } });
    toast(`Reminder sent to ${r.recipients} tutor${r.recipients === 1 ? '' : 's'}.`);
    if (parseHash().path === '/staff/reminders') render();
  },
  async 'run-reminders'() {
    const r = await api('/api/staff/reminders/run', { method: 'POST', body: {} });
    toast(r.sent.length ? r.sent.map((x) => `${x.kind.replace('_', ' ')}: ${x.recipients} tutor(s)`).join(' · ') : 'Nothing due today — every scheduled reminder for this period has already gone out.');
    render();
  },
  'ov-filter'(el) { state.ovFilter = el.dataset.status; renderOverviewRows(); },
  'new-student'() {
    openDialog(html`<form><h2>Add a student</h2>${studentForm()}
      <div class="dialog-actions"><button type="button" class="btn" data-action="close">Cancel</button><button type="submit" class="btn primary">Add student</button></div></form>`,
    async (data) => {
      const r = await api('/api/staff/students', { method: 'POST', body: data });
      closeDialog(); toast('Student added. Now assign a tutor.'); go(`#/staff/students/${r.id}`);
    });
  },
  'edit-student'() {
    const s = state.studentPage.d.student;
    openDialog(html`<form><h2>Edit ${s.first_name} ${s.last_name}</h2>${studentForm(s)}
      <div class="dialog-actions"><button type="button" class="btn" data-action="close">Cancel</button><button type="submit" class="btn primary">Save</button></div></form>`,
    async (data) => { await api(`/api/staff/students/${s.id}`, { method: 'PUT', body: data }); closeDialog(); toast('Saved.'); render(); });
  },
  async 'student-status'(el) {
    const s = state.studentPage.d.student;
    await api(`/api/staff/students/${s.id}/status`, { method: 'POST', body: { status: el.dataset.status } });
    toast(el.dataset.status === 'paused' ? 'Student paused.' : 'Student resumed.');
    render();
  },
  'drop-student'() {
    const s = state.studentPage.d.student;
    openDialog(html`<form><h2>Drop ${s.first_name} ${s.last_name}?</h2><div class="error" hidden></div>
      <div class="banner alert">${icon('alert')}<div><b>A drop is permanent.</b><p>All current tutor assignments end on the date below. Only staff can readmit the student later. Use <b>Pause</b> instead if they're just taking a break.</p></div></div>
      <label class="field"><span>Date left</span><input class="input" type="date" name="date" value="${today()}" max="${today()}" required></label>
      <label class="field"><span>Reason</span><input class="input" name="reason" required placeholder="e.g. Moved out of the area"></label>
      <div class="dialog-actions"><button type="button" class="btn" data-action="close">Cancel</button><button type="submit" class="btn danger solid">Drop student</button></div></form>`,
    async (data) => { await api(`/api/staff/students/${s.id}/status`, { method: 'POST', body: { status: 'dropped', ...data } }); closeDialog(); toast('Student dropped.'); render(); });
  },
  async 'readmit-student'() {
    const s = state.studentPage.d.student;
    const ok = await confirmDialog({ title: `Readmit ${s.first_name}?`, body: html`<p>${s.first_name} left on ${fmtDate(s.left_on, { month: 'long', day: 'numeric', year: 'numeric' })} (${s.leave_reason}). Readmitting is an admin decision and is recorded in the activity log. You'll need to assign a tutor again.</p>`, confirm: 'Readmit student' });
    if (!ok) return;
    await api(`/api/staff/students/${s.id}/status`, { method: 'POST', body: { status: 'active', readmit: true } });
    toast('Student readmitted.'); render();
  },
  'assign-tutor'() { const { d, activeTutors } = state.studentPage; assignmentDialog(d.student, activeTutors); },
  'edit-assignment'(el) { const { d, activeTutors } = state.studentPage; assignmentDialog(d.student, activeTutors, d.assignments.find((a) => a.id === Number(el.dataset.id))); },
  'end-assignment'(el) {
    const { d } = state.studentPage;
    const a = d.assignments.find((x) => x.id === Number(el.dataset.id));
    openDialog(html`<form><h2>End ${a.tutor_name}'s assignment?</h2><div class="error" hidden></div>
      <p class="small muted" style="margin-top:0">The tutor keeps access to months up to the end date so they can finish reporting.</p>
      <label class="field"><span>Last day</span><input class="input" type="date" name="end_date" value="${today()}" min="${a.start_date}" required></label>
      <div class="dialog-actions"><button type="button" class="btn" data-action="close">Cancel</button><button type="submit" class="btn danger solid">End assignment</button></div></form>`,
    async (data) => { await api(`/api/staff/assignments/${a.id}/end`, { method: 'POST', body: data }); closeDialog(); toast('Assignment ended.'); render(); });
  },
  'new-account': () => accountDialog(),
  async 'send-link'(el) {
    const u = state.tutors.find((x) => x.id === Number(el.dataset.id));
    const r = await api(`/api/staff/tutors/${u.id}/send-link`, { method: 'POST', body: {} });
    closeDialog();
    toast(`${r.purpose === 'invite' ? 'Invitation' : 'Sign-in link'} emailed to ${u.email}${emailNote(r.email)}.`);
  },
  'edit-account': (el) => accountDialog(state.tutors.find((u) => u.id === Number(el.dataset.id))),
  async 'reset-password'(el) {
    const u = state.tutors.find((x) => x.id === Number(el.dataset.id));
    const r = await api(`/api/staff/tutors/${u.id}/reset-password`, { method: 'POST', body: {} });
    showTempPassword(u.name, u.email, r.temp_password, false);
  },
};

document.addEventListener('click', async (e) => {
  const el = e.target.closest('[data-action]');
  if (el && actions[el.dataset.action]) {
    e.preventDefault();
    try { await actions[el.dataset.action](el, e); } catch (err) { if (!err.silent) (dialog.open ? dialogError : (m) => toast(m, 'error'))(err.message); }
    return;
  }
  const row = e.target.closest('tr[data-href]');
  if (row) location.hash = row.dataset.href;
  if (!e.target.closest('.notif-panel') && !e.target.closest('[data-action="notif"]')) closeNotif();
});
document.addEventListener('keydown', (e) => {
  const row = e.target.closest && e.target.closest('tr[data-href]');
  if (row && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); location.hash = row.dataset.href; }
});

render();
