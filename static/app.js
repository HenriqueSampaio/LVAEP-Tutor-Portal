'use strict';
/* LVAEP tutor reporting prototype — single-page app (no build step, no dependencies). */

const $ = (sel, el = document) => el.querySelector(sel);
const app = $('#app');
const topbar = $('#topbar');
const dialog = $('#dialog');
const state = { me: null, unread: 0, pending: 0, meta: null, overview: null, ovFilter: 'all', ovSearch: '',
  cal: null, calEvents: new Map(), calTutors: null, calTutor: null, calShowRejected: false, sheet: null };

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
const CAL_STATUS = { pending: 'Pending', confirmed: 'Confirmed', rejected: 'Rejected', cancelled: 'Cancelled' };
const calChip = (s) => html`<span class="chip cal-${s}">${CAL_STATUS[s] || s}</span>`;
const addDays = (iso, n) => { const d = parseD(iso); d.setDate(d.getDate() + n); return isoD(d); };
const weekStart = (iso) => addDays(iso, -parseD(iso).getDay());
const validISO = (s) => /^\d{4}-\d{2}-\d{2}$/.test(s || '') && isoD(parseD(s)) === s;
const toMin = (t) => { const [h, m] = t.split(':').map(Number); return h * 60 + m; };
const fmtTime = (t) => { const [h, m] = t.split(':').map(Number); return `${h % 12 || 12}:${String(m).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`; };
const fmtRange = (a, b) => {
  const [x, y] = [fmtTime(a), fmtTime(b)];
  return x.slice(-2) === y.slice(-2) ? `${x.slice(0, -3)} – ${y}` : `${x} – ${y}`;
};

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
  clearPrintSheet();
  const { path, q } = parseHash();
  try {
    if (!state.meta) state.meta = await api('/api/meta');
    if (path === '/login') return viewLogin();
    if (!state.me) {
      const r = await api('/api/me');
      state.me = r.user; state.unread = r.unread; state.pending = r.pending_requests;
    }
    if (state.me.must_change_password && path !== '/password') return go('#/password');
    renderTopbar(path);
    const staff = isStaff();
    let m;
    if (path === '/password') return viewPassword();
    if (path === '/calendar') return await viewCalendar(q);
    if (path === '/calendar/requests') return await viewRequests();
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
  const requests = html`Requests${state.pending ? html` <span class="nav-count">${state.pending}</span>` : ''}`;
  const nav = staff ? [['/staff', 'Monthly reports'], ['/calendar', 'Calendar'], ['/staff/students', 'Students'],
    ['/staff/tutors', 'Tutors & accounts'], ['/staff/reminders', 'Reminders'], ['/staff/activity', 'Activity log']]
    : [['/tutor', 'My students'], ['/calendar', 'Calendar'], ['/calendar/requests', requests]];
  const active = (p) => path === p || (p === '/staff' && path.startsWith('/staff/report')) || (p === '/staff/students' && path.startsWith('/staff/students/'))
    || (p === '/tutor' && path.startsWith('/tutor/')) || (staff && p === '/calendar' && path === '/calendar/requests');
  topbar.innerHTML = String(html`<div class="topbar-inner">
    <a class="brand" href="#/"><img src="/favicon.svg" alt=""><span>LVAEP Tutor Hours<small>Literacy Volunteers · Essex &amp; Passaic</small></span></a>
    <span class="spacer"></span>
    <div class="user-chip"><b>${state.me.name}</b>${staff ? 'Staff' : 'Tutor'}</div>
    <button class="icon-btn" data-action="notif" aria-label="Notifications${state.unread ? ` (${state.unread} unread)` : ''}">${icon('bell')}${state.unread ? html`<span class="badge">${state.unread}</span>` : ''}</button>
    <a class="icon-btn" href="#/password" aria-label="Change password" title="Change password"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg></a>
    <button class="icon-btn" data-action="logout" aria-label="Sign out" title="Sign out">${icon('logout')}</button>
  </div>
  <div class="subnav"><nav class="topnav" aria-label="${staff ? 'Staff' : 'Tutor'}">${nav.map(([p, label]) => html`<a href="#${p}" ${active(p) ? raw('aria-current="page"') : ''}>${label}</a>`)}</nav></div>`);
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
    <p class="small muted" style="margin:14px 0 0">Forgot your password? Ask LVAEP staff to reset it.</p>
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
      state.unread = me.unread; state.pending = me.pending_requests;
      go(r.user.must_change_password ? '#/password' : '#/');
    } catch (err) {
      const box = $('#login-form .error');
      box.textContent = err.message; box.hidden = false;
    }
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
  if (state.pending) {
    banners.push(html`<div class="banner info">${icon('cal')}<div><b>Staff proposed ${state.pending} session${state.pending === 1 ? '' : 's'} for your calendar</b>
      <p>Approve the ones that work for you. <a href="#/calendar/requests">Review requests →</a></p></div></div>`);
  }
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
      <details class="card panel" ${r.achievements.length || r.achievement_other || r.achievement_notes ? raw('open') : ''}>
        <summary>Achievements this month <span class="muted small" style="font-weight:400">${r.achievements.length + (r.achievement_other ? 1 : 0) ? `· ${r.achievements.length + (r.achievement_other ? 1 : 0)} selected` : '· optional'}</span><span class="spacer"></span><span class="small muted save-state" aria-live="polite"></span></summary>
        <div class="panel-body">
          <p class="small muted" style="margin-top:0">Check each goal the student attained this month. The printed form ticks every goal attained so far this fiscal year.</p>
          ${state.meta.achievement_groups.map((g) => html`<fieldset class="goal-group"><legend>${g.heading}</legend>
            ${g.items.map((x) => html`<label class="check"><input type="checkbox" name="achievement" value="${x}" ${achieved.has(x) ? raw('checked') : ''} ${dis}><span>${x}</span></label>`)}</fieldset>`)}
          ${extras.length ? html`<fieldset class="goal-group"><legend>From the earlier checklist</legend>
            ${extras.map((x) => html`<label class="check"><input type="checkbox" name="achievement" value="${x}" checked ${dis}><span>${x}</span></label>`)}</fieldset>` : ''}
          <label class="field"><span>E. Other(s) <span class="hint">· optional</span></span>
            <input class="input" name="achievement_other" value="${r.achievement_other}" maxlength="300" ${dis} placeholder="Another goal the student reached"></label>
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
      <button class="btn" data-action="print-sheet" title="Print LVAEP's attendance & achievement form (${navigator.platform.startsWith('Mac') ? '⌘P' : 'Ctrl+P'})">${icon('print')} Print form</button>
      ${reportActions(b, staff)}
    </div>
  `, true);

  if (canEdit) {
    const form = $('#report-form');
    form.addEventListener('change', () => saveReportForm(form));
  }
  loadPrintSheet(tutorId, studentId, month);
}

/* ---------- printing the official form (button, Cmd/Ctrl+P, or the browser's own Print) ---------- */
function loadPrintSheet(tutorId, studentId, month) {
  const sheet = { tutorId, studentId, month };
  sheet.ready = fetch(`/print?tutor=${tutorId}&student=${studentId}&month=${month}&fragment=1`)
    .then((res) => (res.ok ? res.text() : Promise.reject(new Error("Couldn't prepare the printable form."))))
    .then((markup) => {
      if (state.sheet !== sheet) return; // the user has moved on to another page
      $('#print-sheet').innerHTML = markup; // server-rendered and escaped (app/exports.py)
      document.body.classList.add('has-sheet');
    });
  sheet.ready.catch(() => {});
  state.sheet = sheet;
}

function clearPrintSheet() {
  state.sheet = null;
  document.body.classList.remove('has-sheet');
  $('#print-sheet').innerHTML = '';
}

async function printSheet() {
  const sheet = state.sheet;
  if (!sheet) return;
  await sheet.ready;
  if (state.sheet === sheet) window.print();
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
          achievement_other: fd.get('achievement_other'), leaving_date: fd.get('leaving_date'), leaving_reason: fd.get('leaving_reason') },
      });
      if (label) label.textContent = 'Saved ✓';
      if (state.sheet) loadPrintSheet(b.tutor.id, b.student.id, b.month);
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

function sessionDialog(b, session, preset = {}) {
  const isNew = !session;
  const range = suggestDate(b);
  const s = session || { date: range.value, attendance: 'present', tutoring_hours: 2, homework_hours: 2, note: '', ...preset };
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
    <p class="small muted">Tutors are assigned students after completing 10 hours of training. New accounts get a temporary password that the person must change at first sign-in.</p>`);
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
      ${isNew ? '' : html`<button type="button" class="btn" data-action="reset-password" data-id="${u.id}" style="margin-right:auto">Reset password</button>`}
      <button type="button" class="btn" data-action="close">Cancel</button>
      <button type="submit" class="btn primary">${isNew ? 'Create account' : 'Save'}</button>
    </div></form>`, async (data) => {
    if (isNew) {
      const r = await api('/api/staff/tutors', { method: 'POST', body: data });
      showTempPassword(data.name, data.email, r.temp_password, true);
    } else {
      await api(`/api/staff/tutors/${u.id}`, { method: 'PUT', body: { ...data, active: !!data.active } });
      closeDialog();
      toast('Account updated.');
      render();
    }
  });
}

function showTempPassword(name, email, pw, created) {
  openDialog(html`<div class="dialog-inner">
    <h2>${created ? 'Account created' : 'Password reset'}</h2>
    <p>Give <b>${name}</b> these sign-in details. They'll choose their own password when they first sign in.</p>
    <dl class="kv"><dt>Sign-in page</dt><dd>${location.origin}</dd><dt>Email</dt><dd>${email}</dd></dl>
    <p class="small muted" style="margin-bottom:6px">Temporary password (shown once):</p>
    <div class="temp-pw">${pw}</div>
    <p class="small muted">In the full release this would be emailed automatically; email delivery isn't configured in the prototype.</p>
    <div class="dialog-actions"><button type="button" class="btn primary" data-action="close-render">Done</button></div></div>`);
}

/* ---------- staff: reminders ---------- */
const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
async function viewReminders() {
  const d = await api('/api/staff/reminders');
  const s = d.settings;
  const cur = thisMonth();
  const prev = shiftMonth(cur, -1);
  const KIND = { month_end: 'Last day of month', overdue: 'Overdue (3rd of month)', weekly: 'Weekly nudge', manual: 'Sent by staff' };
  paint(html`
    <div class="page-head"><div><h1>Reminders</h1><p class="muted" style="margin:2px 0 0">So staff don't have to chase tutors for their hours.</p></div></div>
    <div class="banner info">${icon('bell')}<div><b>Reminders appear in each tutor's notification bell.</b><p>Email/SMS delivery isn't connected in this prototype — each reminder is recorded so it can be sent by email once LVAEP picks a provider.</p></div></div>
    <div class="cards" style="grid-template-columns:repeat(auto-fit,minmax(320px,1fr))">
      <section class="card card-pad"><h2>Automatic reminders</h2>
        <form id="rem-form">
          <label class="switch"><input type="checkbox" name="reminder_month_end" ${s.reminder_month_end === '1' ? raw('checked') : ''}><span><b>Last day of the month</b><br><span class="small muted">“It's the last day of October — don't forget to submit your hours.” Sent to tutors who haven't submitted.</span></span></label>
          <label class="switch"><input type="checkbox" name="reminder_overdue" ${s.reminder_overdue === '1' ? raw('checked') : ''}><span><b>Overdue follow-up</b><br><span class="small muted">On the 3rd, tutors who still haven't submitted last month get a second reminder.</span></span></label>
          <label class="switch"><input type="checkbox" name="reminder_weekly" ${s.reminder_weekly === '1' ? raw('checked') : ''}><span><b>Weekly nudge</b><br><span class="small muted">Tutors who logged nothing in the past 7 days get a reminder on
            <select class="input" name="reminder_weekly_day" style="display:inline-block;width:auto;min-height:32px;padding:2px 8px">${WEEKDAYS.map((w, i) => html`<option value="${i}" ${String(i) === s.reminder_weekly_day ? raw('selected') : ''}>${w}</option>`)}</select>.</span></span></label>
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
      ${d.runs.length ? '' : html`<tr><td colspan="5" class="empty">No reminders sent yet.</td></tr>`}</tbody></table></div>`);
  $('#rem-form').addEventListener('change', async (e) => {
    const f = e.currentTarget;
    await api('/api/staff/reminders/settings', { method: 'PUT', body: {
      reminder_month_end: f.reminder_month_end.checked ? '1' : '0', reminder_overdue: f.reminder_overdue.checked ? '1' : '0',
      reminder_weekly: f.reminder_weekly.checked ? '1' : '0', reminder_weekly_day: f.reminder_weekly_day.value } });
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

/* ---------- calendar (scheduled sessions) ---------- */
const CAL_VIEWS = { month: 'Month', week: 'Week', day: 'Day' };
const CAL_WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

function calRange(view, date) {
  if (view === 'day') return [date, date];
  if (view === 'week') { const s = weekStart(date); return [s, addDays(s, 6)]; }
  const m = date.slice(0, 7);
  return [weekStart(`${m}-01`), addDays(weekStart(monthEnd(m)), 6)];
}
function calShift(view, date, dir) {
  if (view === 'month') return `${shiftMonth(date.slice(0, 7), dir)}-01`;
  return addDays(date, dir * (view === 'week' ? 7 : 1));
}
function calHref(o) {
  const { view, date, tutor } = { ...state.cal, ...o };
  return `#/calendar?view=${view}&date=${date}${isStaff() && tutor ? `&tutor=${tutor}` : ''}`;
}
const eventWho = (e) => `${state.cal && state.cal.tutor === 'all' ? `${e.tutor_name}: ` : ''}${e.students.map((s) => s.name).join(', ')}`;
const eventTitle = (e) => `${fmtRange(e.start_time, e.end_time)} · ${eventWho(e)} · ${CAL_STATUS[e.status]}`;
const hourLabel = (h) => `${h % 12 || 12} ${h < 12 || h === 24 ? 'AM' : 'PM'}`;

async function viewCalendar(q) {
  const staff = isStaff();
  const view = CAL_VIEWS[q.view] ? q.view : 'week';
  const date = validISO(q.date) ? q.date : today();
  let tutor = null;
  if (staff) {
    const { items } = await api('/api/staff/tutors');
    state.calTutors = items.filter((u) => u.role === 'tutor' && u.active);
    tutor = q.tutor || state.calTutor || (state.calTutors[0] ? String(state.calTutors[0].id) : 'all');
    if (tutor !== 'all' && !items.some((u) => String(u.id) === tutor && u.role === 'tutor')) tutor = 'all';
    state.calTutor = tutor;
  }
  const [start, end] = calRange(view, date);
  const d = await api(`/api/calendar?start=${start}&end=${end}${staff ? `&tutor_id=${tutor}` : ''}`);
  state.cal = { view, date, tutor, start, end };
  state.calEvents = new Map(d.events.map((e) => [e.id, e]));
  const events = d.events.filter((e) => state.calShowRejected || e.status !== 'rejected');
  const days = [];
  for (let x = start; x <= end; x = addDays(x, 1)) days.push(x);
  const title = view === 'month' ? monthLabel(date.slice(0, 7))
    : view === 'week' ? `${fmtDate(start, { month: 'short', day: 'numeric' })} – ${fmtDate(end, { month: 'short', day: 'numeric', year: 'numeric' })}`
      : fmtDate(date, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
  const tutorName = staff && tutor !== 'all' ? (calTutorName(tutor) || 'Tutor') : null;
  const waiting = d.events.filter((e) => e.status === 'pending').length;

  paint(html`
    <div class="page-head">
      <div><h1>${staff ? (tutorName ? `${tutorName}'s calendar` : 'All tutors') : 'Your calendar'}</h1>
        <p class="muted" style="margin:2px 0 0">${staff ? 'Sessions you propose are pending until the tutor approves them.' : 'Sessions you add are confirmed right away. Staff proposals wait for your approval.'}</p></div>
      <span class="spacer"></span>
      ${staff ? html`<a class="btn" href="#/calendar/requests">Your proposals</a>`
    : html`<a class="btn" href="#/calendar/requests">Requests${state.pending ? html` <span class="nav-count">${state.pending}</span>` : ''}</a>`}
      <button class="btn primary" data-action="cal-new">${icon('plus')} ${staff ? 'Propose session' : 'New session'}</button>
    </div>
    ${!staff && waiting ? html`<div class="banner info">${icon('cal')}<div><b>${waiting} proposed session${waiting === 1 ? ' is' : 's are'} waiting for you in this view</b>
      <p>Pending sessions have a dashed outline. Open one to approve or reject it, or <a href="#/calendar/requests">review all requests</a>.</p></div></div>` : ''}
    <div class="cal-toolbar">
      <div class="cal-nav">
        <a class="btn sm" href="${calHref({ date: calShift(view, date, -1) })}" aria-label="Previous ${view}">‹</a>
        <a class="btn sm" href="${calHref({ date: today() })}">Today</a>
        <a class="btn sm" href="${calHref({ date: calShift(view, date, 1) })}" aria-label="Next ${view}">›</a>
      </div>
      <h2 class="cal-title">${title}</h2>
      <span class="spacer"></span>
      ${staff ? html`<select class="input" id="cal-tutor" aria-label="Tutor">
        <option value="all" ${tutor === 'all' ? raw('selected') : ''}>All tutors</option>
        ${state.calTutors.map((t) => html`<option value="${t.id}" ${String(t.id) === tutor ? raw('selected') : ''}>${t.name}</option>`)}</select>` : ''}
      <nav class="cal-views" aria-label="Calendar view">${Object.entries(CAL_VIEWS).map(([k, v]) => html`<a href="${calHref({ view: k })}" ${k === view ? raw('aria-current="page"') : ''}>${v}</a>`)}</nav>
      <label class="check cal-toggle"><input type="checkbox" id="cal-rejected" ${state.calShowRejected ? raw('checked') : ''}><span>Show rejected</span></label>
    </div>
    ${view === 'month' ? calMonth(days, events)
    : view === 'week' ? html`<div class="cal-wide">${calGrid(days, events)}</div><div class="cal-narrow">${calAgenda(days, events)}</div>`
      : calGrid(days, events)}
    ${events.length ? '' : html`<p class="muted small" style="margin-top:10px">Nothing scheduled ${view === 'day' ? 'on this day' : `this ${view}`}.${view === 'month' ? '' : ' Click an empty time to add a session.'}</p>`}
    <div class="cal-legend">${Object.entries(CAL_STATUS).filter(([k]) => k !== 'rejected' || state.calShowRejected).map(([k, v]) => html`<span><i class="${k}"></i>${v}</span>`)}</div>
  `);
  const sel = $('#cal-tutor');
  if (sel) sel.addEventListener('change', () => { state.calTutor = sel.value; go(calHref({ tutor: sel.value })); });
  $('#cal-rejected').addEventListener('change', (e) => { state.calShowRejected = e.target.checked; render(); });
  if (q.event) {
    // Opened from a notification: show the session once, then drop it from the URL so later renders don't reopen it.
    history.replaceState(null, '', calHref({}));
    const ev = state.calEvents.get(Number(q.event));
    if (ev) eventDialog(ev);
  }
}

function calTutorName(id) {
  const t = (state.calTutors || []).find((u) => String(u.id) === String(id));
  return t && t.name;
}

function byDate(events) {
  const out = {};
  events.forEach((e) => { (out[e.date] = out[e.date] || []).push(e); });
  return out;
}

function calMonth(days, events) {
  const month = state.cal.date.slice(0, 7);
  const map = byDate(events);
  return html`<div class="card cal-month">
    ${CAL_WEEKDAYS.map((w) => html`<div class="cal-wd">${w}</div>`)}
    ${days.map((day) => {
    const list = map[day] || [];
    const dayHref = calHref({ view: 'day', date: day });
    return html`<div class="cal-cell ${day.slice(0, 7) !== month ? 'out' : ''} ${day === today() ? 'today' : ''}">
      <a class="cal-num" href="${dayHref}" aria-label="${fmtDate(day, { weekday: 'long', month: 'long', day: 'numeric' })}${list.length ? `, ${list.length} session${list.length === 1 ? '' : 's'}` : ''}">${parseD(day).getDate()}</a>
      <div class="cal-pills">${list.slice(0, 3).map((e) => html`<button type="button" class="cal-pill ${e.status}" data-action="cal-event" data-id="${e.id}" title="${eventTitle(e)}">
        <b>${fmtTime(e.start_time).replace(':00', '')}</b> ${eventWho(e)}<span class="sr-only"> (${CAL_STATUS[e.status]})</span></button>`)}
        ${list.length > 3 ? html`<a class="cal-more" href="${dayHref}">+${list.length - 3} more</a>` : ''}</div>
      ${list.length ? html`<a class="cal-dots" href="${dayHref}" tabindex="-1" aria-hidden="true">${list.slice(0, 4).map((e) => html`<i class="${e.status}"></i>`)}</a>` : ''}
    </div>`;
  })}</div>`;
}

/** Side-by-side lanes for overlapping events: id -> { lane, lanes }. */
function layoutLanes(list) {
  const out = new Map();
  const sorted = [...list].sort((a, b) => toMin(a.start_time) - toMin(b.start_time) || toMin(b.end_time) - toMin(a.end_time));
  let cluster = []; let laneEnds = []; let clusterEnd = -1;
  const flush = () => { cluster.forEach((id) => { out.get(id).lanes = laneEnds.length; }); cluster = []; laneEnds = []; };
  for (const e of sorted) {
    const s = toMin(e.start_time); const en = toMin(e.end_time);
    if (s >= clusterEnd) flush();
    let lane = laneEnds.findIndex((x) => x <= s);
    if (lane === -1) { lane = laneEnds.length; laneEnds.push(en); } else laneEnds[lane] = en;
    out.set(e.id, { lane, lanes: 1 });
    cluster.push(e.id);
    clusterEnd = Math.max(clusterEnd, en);
  }
  flush();
  return out;
}

function calGrid(days, events) {
  const startH = Math.min(7, ...events.map((e) => Math.floor(toMin(e.start_time) / 60)));
  const endH = Math.max(21, ...events.map((e) => Math.ceil(toMin(e.end_time) / 60)));
  const hours = [];
  for (let h = startH; h < endH; h += 1) hours.push(h);
  const map = byDate(events);
  return html`<div class="card cal-grid ${days.length === 1 ? 'single' : ''}" style="--rows:${endH - startH};--cols:${days.length}">
    <div class="cal-grid-head"><div></div>${days.map((d) => html`<a href="${calHref({ view: 'day', date: d })}" class="${d === today() ? 'today' : ''}"><span>${fmtDate(d, { weekday: 'short' })}</span><b>${parseD(d).getDate()}</b></a>`)}</div>
    <div class="cal-grid-body">
      <div class="cal-times" aria-hidden="true">${hours.map((h) => html`<div>${hourLabel(h)}</div>`)}</div>
      ${days.map((d) => {
    const list = map[d] || [];
    const lanes = layoutLanes(list);
    return html`<div class="cal-col ${d === today() ? 'today' : ''}" data-action="cal-slot" data-date="${d}" data-start="${startH}" data-rows="${endH - startH}">
        ${list.map((e) => {
      const { lane, lanes: n } = lanes.get(e.id);
      const top = (toMin(e.start_time) - startH * 60) / 60;
      const len = (toMin(e.end_time) - toMin(e.start_time)) / 60;
      // short blocks drop the status chip (the color still shows it); half-hour ones go on one line
      const fit = len <= 0.5 ? 'short tiny' : len < 1 ? 'short' : '';
      return html`<button type="button" class="cal-event ${e.status} ${fit}" data-action="cal-event" data-id="${e.id}" title="${eventTitle(e)}"
          style="top:calc(${top} * var(--hour));height:calc(${len} * var(--hour));left:calc(${lane} * 100% / ${n});width:calc(100% / ${n})">
          <span class="t">${len <= 0.5 ? fmtTime(e.start_time) : fmtRange(e.start_time, e.end_time)}</span><span class="w">${eventWho(e)}</span>${calChip(e.status)}</button>`;
    })}</div>`;
  })}
    </div></div>`;
}

function calAgenda(days, events) {
  const map = byDate(events);
  return html`<div class="card cal-agenda">${days.map((d) => html`<section class="${d === today() ? 'today' : ''}">
    <h3><a href="${calHref({ view: 'day', date: d })}">${fmtDate(d, { weekday: 'long', month: 'short', day: 'numeric' })}</a></h3>
    ${(map[d] || []).length ? map[d].map((e) => html`<button type="button" class="cal-item ${e.status}" data-action="cal-event" data-id="${e.id}">
      <span class="t">${fmtRange(e.start_time, e.end_time)}</span><span class="w">${eventWho(e)}</span>${calChip(e.status)}</button>`)
    : html`<p class="muted small" style="margin:4px 0 0">Nothing scheduled</p>`}
  </section>`)}</div>`;
}

function eventDialog(ev) {
  const staff = isStaff();
  const a = ev.actions;
  const proposed = ev.origin === 'staff';
  const mins = toMin(ev.end_time) - toMin(ev.start_time);
  const length = `${Math.floor(mins / 60) ? `${Math.floor(mins / 60)} h` : ''}${mins % 60 ? ` ${mins % 60} min` : ''}`.trim();
  const withdraw = staff && ev.status === 'pending' && ev.created_by === state.me.id;
  openDialog(html`<div class="dialog-inner">
    <div class="row" style="margin-bottom:8px">${calChip(ev.status)}${proposed ? html`<span class="chip neutral">Proposed by staff</span>` : ''}</div>
    <h2>${ev.students.map((s) => s.name).join(', ')}</h2>
    <div class="error" hidden></div>
    <dl class="cal-dl">
      <div><dt>When</dt><dd>${fmtDate(ev.date, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}<br>${fmtRange(ev.start_time, ev.end_time)} <span class="muted">(${length})</span></dd></div>
      <div><dt>Tutor</dt><dd>${ev.tutor_name}</dd></div>
      ${ev.notes ? html`<div><dt>Notes</dt><dd class="pre">${ev.notes}</dd></div>` : ''}
      <div><dt>${proposed ? 'Proposed by' : 'Added by'}</dt><dd>${ev.created_by_name} · ${fmtDT(ev.created_at)}</dd></div>
      ${ev.responded_at ? html`<div><dt>${ev.status === 'rejected' ? 'Rejected' : 'Approved'}</dt><dd>${ev.responded_by_name} · ${fmtDT(ev.responded_at)}${ev.response_note ? html`<br>“${ev.response_note}”` : ''}</dd></div>` : ''}
      ${ev.cancelled_at ? html`<div><dt>Cancelled</dt><dd>${ev.cancelled_by_name} · ${fmtDT(ev.cancelled_at)}${ev.cancel_reason ? html`<br>“${ev.cancel_reason}”` : ''}</dd></div>` : ''}
    </dl>
    ${ev.status === 'pending' && !a.includes('approve') ? html`<p class="small muted" style="margin-bottom:0">Waiting for ${ev.tutor_name} to approve or reject it.</p>` : ''}
    ${a.includes('log_hours') ? html`<div class="cal-log"><b class="small">Log hours for the monthly report</b>
      <div class="row" style="margin-top:6px">${ev.students.map((s) => html`<button type="button" class="btn sm" data-action="cal-log" data-id="${ev.id}" data-student="${s.id}">${icon('plus')} ${s.name}</button>`)}</div></div>` : ''}
    <div class="dialog-actions">
      ${a.includes('cancel') ? html`<button type="button" class="btn danger" data-action="cal-cancel" data-id="${ev.id}" style="margin-right:auto">${withdraw ? 'Withdraw proposal' : 'Cancel session'}</button>` : ''}
      <button type="button" class="btn" data-action="close">Close</button>
      ${a.includes('edit') ? html`<button type="button" class="btn" data-action="cal-edit" data-id="${ev.id}">Edit</button>` : ''}
      ${a.includes('reject') ? html`<button type="button" class="btn danger" data-action="cal-reject" data-id="${ev.id}">Reject</button>` : ''}
      ${a.includes('approve') ? html`<button type="button" class="btn primary" data-action="cal-approve" data-id="${ev.id}">${icon('check')} Approve</button>` : ''}
    </div></div>`);
}

async function eventForm(ev, defaults = {}) {
  const staff = isStaff();
  const isNew = !ev;
  if (staff && !state.calTutors) state.calTutors = (await api('/api/staff/tutors')).items.filter((u) => u.role === 'tutor' && u.active);
  const calTutor = state.cal && state.cal.tutor !== 'all' ? Number(state.cal.tutor) : null;
  const tutorId = ev ? ev.tutor_id : staff ? (calTutor || (state.calTutors[0] && state.calTutors[0].id)) : state.me.id;
  const v = ev || { date: defaults.date || today(), start_time: defaults.start || '16:00', end_time: defaults.end || '17:00', notes: '', students: [] };
  openDialog(html`<form id="ev-form">
    <h2>${isNew ? (staff ? 'Propose a session' : 'New session') : 'Edit session'}</h2>
    <div class="error" hidden></div>
    ${staff && isNew ? html`<label class="field"><span>Tutor</span><select class="input" name="tutor_id" required>
      ${state.calTutors.map((t) => html`<option value="${t.id}" ${t.id === tutorId ? raw('selected') : ''}>${t.name}</option>`)}</select></label>`
    : staff ? html`<p class="small muted" style="margin-top:0">Tutor: <b>${ev.tutor_name}</b></p><input type="hidden" name="tutor_id" value="${ev.tutor_id}">` : ''}
    <label class="field"><span>Date</span><input class="input" type="date" name="date" value="${v.date}" ${staff ? raw(`min="${today()}"`) : ''} required></label>
    <div class="grid-2">
      <label class="field"><span>Start time</span><input class="input" type="time" name="start_time" value="${v.start_time}" step="900" required></label>
      <label class="field"><span>End time</span><input class="input" type="time" name="end_time" value="${v.end_time}" step="900" required></label>
    </div>
    <fieldset class="field cal-students"><legend>Students</legend><div id="ev-students" class="muted small">Loading students…</div></fieldset>
    <label class="field"><span>Notes <span class="hint">· optional</span></span><textarea class="input" name="notes" maxlength="1000" placeholder="What will you work on?">${v.notes}</textarea></label>
    ${staff ? html`<p class="small muted">The tutor gets a notification and must approve this session before it's confirmed.</p>` : ''}
    <div class="dialog-actions"><button type="button" class="btn" data-action="close">Cancel</button>
      <button type="submit" class="btn primary">${isNew ? (staff ? 'Send proposal' : 'Add session') : 'Save changes'}</button></div>
  </form>`, async (data, form) => {
    const studentIds = [...form.querySelectorAll('input[name="student_ids"]:checked')].map((i) => Number(i.value));
    if (!studentIds.length) throw new Error('Choose at least one student.');
    if (!data.start_time || !data.end_time || data.end_time <= data.start_time) throw new Error('The end time must be after the start time.');
    const body = { date: data.date, start_time: data.start_time, end_time: data.end_time, notes: data.notes, student_ids: studentIds };
    if (staff) body.tutor_id = Number(data.tutor_id);
    const r = isNew ? await api('/api/calendar', { method: 'POST', body }) : await api(`/api/calendar/${ev.id}`, { method: 'PUT', body });
    closeDialog();
    toast(!isNew ? 'Session updated.' : staff ? `Proposal sent to ${r.event.tutor_name} for approval.` : 'Session added to your calendar.');
    if (parseHash().path === '/calendar') {
      const tutor = staff && state.cal.tutor !== 'all' ? String(r.event.tutor_id) : state.cal.tutor;
      go(calHref({ date: r.event.date, tutor }));
    } else render();
  });
  loadEventStudents(v.students.map((s) => s.id));
}

let evStudentsReq = 0;
async function loadEventStudents(selected = []) {
  const form = $('#ev-form');
  if (!form) return;
  const tutor = form.elements.tutor_id ? form.elements.tutor_id.value : state.me.id;
  const date = form.elements.date.value || today();
  const keep = new Set([...selected, ...[...form.querySelectorAll('input[name="student_ids"]:checked')].map((i) => Number(i.value))]);
  const req = ++evStudentsReq;
  const box = $('#ev-students');
  try {
    const { items } = await api(`/api/calendar/students?tutor_id=${tutor}&date=${date}`);
    if (req !== evStudentsReq || !$('#ev-form')) return;
    box.className = '';
    box.innerHTML = String(items.length ? html`${items.map((s) => html`<label class="check"><input type="checkbox" name="student_ids" value="${s.id}" ${keep.has(s.id) || items.length === 1 ? raw('checked') : ''}><span>${s.name}${studentChip(s.status)}</span></label>`)}`
      : html`<span class="muted small">No students are assigned to this tutor on ${fmtDate(date)}.</span>`);
  } catch (err) { if (req === evStudentsReq) box.textContent = err.message; }
}

dialog.addEventListener('change', (e) => {
  if (e.target.closest('#ev-form') && ['tutor_id', 'date'].includes(e.target.name)) loadEventStudents();
});

function newEventDefaults() {
  const c = state.cal;
  let date = !c ? today() : c.view === 'day' ? c.date : (today() >= c.start && today() <= c.end ? today() : c.date);
  if (isStaff() && date < today()) date = today();
  return { date };
}

/* ---------- calendar: requests & proposals ---------- */
async function viewRequests() {
  const staff = isStaff();
  const { events } = await api('/api/calendar/requests');
  state.calEvents = new Map(events.map((e) => [e.id, e]));
  if (!staff) {
    state.pending = events.length;
    renderTopbar('/calendar/requests');
    paint(html`
      <div class="page-head"><div><h1>Session requests</h1>
        <p class="muted" style="margin:2px 0 0">LVAEP staff proposed these sessions for your calendar. Approve the ones that work for you.</p></div>
        <span class="spacer"></span><a class="btn" href="#/calendar">${icon('cal')} Open calendar</a></div>
      ${events.length ? html`<div class="cards">${events.map((e) => html`<article class="card request-card">
        <header><div class="cal-when"><b>${fmtDate(e.date, { weekday: 'long', month: 'short', day: 'numeric' })}</b><span>${fmtRange(e.start_time, e.end_time)}</span></div>
          <span class="spacer"></span>${calChip(e.status)}</header>
        <div><b>${e.students.map((s) => s.name).join(', ')}</b></div>
        ${e.notes ? html`<p class="small" style="margin:0;color:var(--ink-2)">${e.notes}</p>` : ''}
        <div class="small muted">Proposed by ${e.created_by_name} · ${fmtDT(e.created_at)}</div>
        <div class="actions">
          <button class="btn primary" data-action="cal-approve" data-id="${e.id}">${icon('check')} Approve</button>
          <button class="btn danger" data-action="cal-reject" data-id="${e.id}">Reject</button>
          <a class="btn ghost" href="#/calendar?view=week&date=${e.date}&event=${e.id}">View</a>
        </div></article>`)}</div>`
    : html`<div class="card empty"><b>No requests waiting.</b><br>When LVAEP staff propose a session, it shows up here for you to approve or reject.</div>`}`);
    return;
  }
  const counts = { pending: 0, confirmed: 0, rejected: 0, cancelled: 0 };
  events.forEach((e) => { counts[e.status] += 1; });
  paint(html`
    <div class="page-head"><div><h1>Your proposals</h1>
      <p class="muted" style="margin:2px 0 0">${counts.pending} waiting · ${counts.confirmed} approved · ${counts.rejected} rejected · ${counts.cancelled} cancelled or withdrawn</p></div>
      <span class="spacer"></span><a class="btn" href="#/calendar">${icon('cal')} Calendar</a>
      <button class="btn primary" data-action="cal-new">${icon('plus')} Propose session</button></div>
    <div class="toolbar"><select class="input" id="rq-status" style="max-width:200px" aria-label="Filter by status"><option value="">All statuses</option>
      ${Object.entries(CAL_STATUS).map(([k, v]) => html`<option value="${k}">${v}</option>`)}</select></div>
    <div class="card table-wrap"><table class="data">
      <thead><tr><th>Date</th><th>Time</th><th>Tutor</th><th>Students</th><th>Status</th><th>Tutor's response</th></tr></thead>
      <tbody id="rq-body">${events.length ? events.map((e) => html`<tr class="clickable" tabindex="0" data-status="${e.status}"
        data-href="#/calendar?view=week&date=${e.date}&tutor=${e.tutor_id}&event=${e.id}">
        <td class="nowrap"><b>${fmtDate(e.date)}</b></td><td class="nowrap">${fmtRange(e.start_time, e.end_time)}</td>
        <td>${e.tutor_name}</td><td>${e.students.map((s) => s.name).join(', ')}</td><td>${calChip(e.status)}</td>
        <td>${e.responded_at ? html`${fmtDT(e.responded_at)}${e.response_note ? html`<div class="sub">“${e.response_note}”</div>` : ''}`
    : e.status === 'cancelled' ? html`<span class="sub">Cancelled ${fmtDT(e.cancelled_at)}</span>` : html`<span class="muted">—</span>`}</td></tr>`)
    : html`<tr><td colspan="6" class="empty">You haven't proposed any sessions yet.</td></tr>`}</tbody>
    </table></div>`);
  $('#rq-status').addEventListener('change', (e) => {
    document.querySelectorAll('#rq-body tr[data-status]').forEach((tr) => { tr.hidden = e.target.value && tr.dataset.status !== e.target.value; });
  });
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
  'edit-account': (el) => accountDialog(state.tutors.find((u) => u.id === Number(el.dataset.id))),
  async 'reset-password'(el) {
    const u = state.tutors.find((x) => x.id === Number(el.dataset.id));
    const r = await api(`/api/staff/tutors/${u.id}/reset-password`, { method: 'POST', body: {} });
    showTempPassword(u.name, u.email, r.temp_password, false);
  },
  'print-sheet': () => printSheet(),
  'cal-event': (el) => eventDialog(state.calEvents.get(Number(el.dataset.id))),
  'cal-new': () => eventForm(null, newEventDefaults()),
  'cal-edit': (el) => eventForm(state.calEvents.get(Number(el.dataset.id))),
  'cal-slot'(el, e) {
    const rect = el.getBoundingClientRect();
    const h = Math.min(23, Number(el.dataset.start) + Math.floor(((e.clientY - rect.top) / rect.height) * Number(el.dataset.rows)));
    const pad = (n) => String(n).padStart(2, '0');
    eventForm(null, { date: el.dataset.date, start: `${pad(h)}:00`, end: h < 23 ? `${pad(h + 1)}:00` : '23:59' });
  },
  async 'cal-approve'(el) {
    const { event } = await api(`/api/calendar/${el.dataset.id}/approve`, { method: 'POST', body: {} });
    closeDialog();
    state.pending = Math.max(0, state.pending - 1);
    toast(`Approved: ${fmtDate(event.date)}, ${fmtRange(event.start_time, event.end_time)}.`);
    render();
  },
  'cal-reject'(el) {
    const ev = state.calEvents.get(Number(el.dataset.id));
    openDialog(html`<form><h2>Reject this session?</h2><div class="error" hidden></div>
      <p class="small muted" style="margin-top:0">${ev.students.map((s) => s.name).join(', ')} · ${fmtDate(ev.date)}, ${fmtRange(ev.start_time, ev.end_time)}. ${ev.created_by_name} will be notified.</p>
      <label class="field"><span>Reason <span class="hint">· optional</span></span><input class="input" name="note" maxlength="500" placeholder="e.g. I'm not available that day"></label>
      <div class="dialog-actions"><button type="button" class="btn" data-action="close">Keep it</button><button type="submit" class="btn danger solid">Reject session</button></div></form>`,
    async (data) => {
      await api(`/api/calendar/${ev.id}/reject`, { method: 'POST', body: data });
      closeDialog();
      state.pending = Math.max(0, state.pending - 1);
      toast('Session rejected.');
      render();
    });
  },
  'cal-cancel'(el) {
    const ev = state.calEvents.get(Number(el.dataset.id));
    const withdraw = isStaff() && ev.status === 'pending' && ev.created_by === state.me.id;
    const notify = isStaff() ? ev.tutor_name : ev.origin === 'staff' ? ev.created_by_name : null;
    openDialog(html`<form><h2>${withdraw ? 'Withdraw this proposal?' : 'Cancel this session?'}</h2><div class="error" hidden></div>
      <p class="small muted" style="margin-top:0">${ev.students.map((s) => s.name).join(', ')} · ${fmtDate(ev.date)}, ${fmtRange(ev.start_time, ev.end_time)}.${notify ? ` ${notify} will be notified.` : ''} The session stays on the calendar, marked cancelled.</p>
      <label class="field"><span>Reason <span class="hint">· optional</span></span><input class="input" name="reason" maxlength="500" placeholder="e.g. Library closed for a holiday"></label>
      <div class="dialog-actions"><button type="button" class="btn" data-action="close">Keep it</button><button type="submit" class="btn danger solid">${withdraw ? 'Withdraw proposal' : 'Cancel session'}</button></div></form>`,
    async (data) => {
      await api(`/api/calendar/${ev.id}/cancel`, { method: 'POST', body: data });
      closeDialog();
      toast(withdraw ? 'Proposal withdrawn.' : 'Session cancelled.');
      render();
    });
  },
  async 'cal-log'(el) {
    const ev = state.calEvents.get(Number(el.dataset.id));
    const b = await api(`/api/reports/${ev.tutor_id}/${el.dataset.student}/${ev.date.slice(0, 7)}`);
    if (b.report.locked) throw new Error(`${b.month_label} is already submitted for ${b.student.name}. Ask LVAEP staff to reopen it.`);
    if (b.sessions.some((s) => s.date === ev.date)) throw new Error(`Hours for ${b.student.name} on ${fmtDate(ev.date)} are already logged. Edit them from the monthly report.`);
    currentBundle = b;
    const hours = Math.min(8, Math.round(((toMin(ev.end_time) - toMin(ev.start_time)) / 60) * 4) / 4);
    sessionDialog(b, null, { date: ev.date, tutoring_hours: hours, homework_hours: 0, note: ev.notes.slice(0, 500) });
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
  if ((e.metaKey || e.ctrlKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === 'p' && state.sheet) {
    e.preventDefault(); // print the student's form, not the screen
    printSheet().catch((err) => toast(err.message, 'error'));
    return;
  }
  const row = e.target.closest && e.target.closest('tr[data-href]');
  if (row && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); location.hash = row.dataset.href; }
});

render();
