'use strict';
/* ═══════════════════════════════════════════════
   connections_dispatch.js
   ConnectionDispatcher — розподіляє заявки на підключення
   по монтажниках (Connector), призначає дату і вікно.

   Доступ: ConnectionDispatcher
   (може суміщатися через additional_roles)
═══════════════════════════════════════════════ */

const S = {
  requests:   [],
  buildings:  [],
  connectors: [],   // users with role=Connector
  selectedId: null,
  schedulingId: null,
  postponingId: null,
};

const el  = id => document.getElementById(id);
const api = (url, opts) => FiberAuth.fetchJson(url, opts);

/* ─── DATE HELPERS ─── */
function dlDays(str) {
  if (!str) return null;
  return Math.ceil((new Date(str) - new Date()) / 86400000);
}
function dlClass(days) {
  if (days === null) return 'dl-ok';
  if (days < 0) return 'dl-over';
  if (days <= 3) return 'dl-soon';
  return 'dl-ok';
}
function dlLabel(str) {
  const days = dlDays(str);
  if (days === null) return '—';
  const d = new Date(str).toLocaleDateString('uk-UA', {day:'numeric', month:'short'});
  if (days < 0)  return `⚠ ${Math.abs(days)} дн. тому`;
  if (days === 0) return 'Сьогодні';
  if (days === 1) return 'Завтра';
  return d;
}
function isToday(str) {
  if (!str) return false;
  const d = new Date(str);
  const n = new Date();
  return d.getFullYear()===n.getFullYear() && d.getMonth()===n.getMonth() && d.getDate()===n.getDate();
}

/* ─── STATUS PILL ─── */
function statusPill(status) {
  const map = {
    new:            ['s-new',      '○', 'Нова'],
    scheduled:      ['s-sched',    '◎', 'Заплановано'],
    in_progress:    ['s-progress', '●', 'В роботі'],
    completed:      ['s-done',     '✓', 'Виконано'],
    postponed:      ['s-postponed','↩', 'Перенесено'],
    no_access:      ['s-no_access','✕', 'Немає доступу'],
    canceled:       ['s-postponed','—', 'Скасовано'],
    technical_issue:['s-no_access','⚠', 'Тех. проблема'],
  };
  const [cls,,label] = map[status] || ['s-new','○',status];
  return `<span class="spill ${cls}"><span class="spill-dot"></span>${label}</span>`;
}

const WINDOWS = { before_lunch:'До обіду (9–13)', after_lunch:'Після обіду (13–18)' };

/* ════════════════════════════════════════
   FILTER
════════════════════════════════════════ */
function filteredRequests() {
  const status = el('fStatus').value;
  const date   = el('fDate').value;
  const now    = new Date();

  return S.requests.filter(r => {
    if (status && r.status !== status) return false;
    if (date) {
      const sd = r.scheduled_date ? new Date(r.scheduled_date) : null;
      if (date === 'today'    && !(sd && isToday(r.scheduled_date))) return false;
      if (date === 'tomorrow') {
        const tom = new Date(now); tom.setDate(tom.getDate()+1);
        if (!sd || sd.toDateString() !== tom.toDateString()) return false;
      }
      if (date === 'week') {
        const weekEnd = new Date(now); weekEnd.setDate(weekEnd.getDate()+7);
        if (!sd || sd < now || sd > weekEnd) return false;
      }
    }
    return true;
  });
}

/* ════════════════════════════════════════
   RENDER: QUEUE
════════════════════════════════════════ */
function renderQueue() {
  const list = filteredRequests();
  el('qCount').textContent = list.length;
  const mount = el('queueList');

  if (!list.length) {
    mount.innerHTML = `<div class="empty"><div class="empty-icon">⊕</div><span>Заявок немає</span></div>`;
    return;
  }

  mount.innerHTML = list.map(r => {
    const days = dlDays(r.deadline_at);
    const urgency = days !== null && days < 0 ? 'overdue' : days !== null && days <= 3 ? 'soon' : '';
    const sel = r.id === S.selectedId ? 'sel' : '';
    const b = S.buildings.find(x => x.id === r.building_id);

    return `
      <div class="rcard ${sel} ${urgency}" data-id="${r.id}">
        <div class="rc-name">${r.customer_name}</div>
        <div class="rc-addr">${b?.address || '—'} · кв. ${r.flat_number}</div>
        <div class="rc-bottom">
          <span class="rc-phone">${r.phone}</span>
          ${statusPill(r.status)}
        </div>
        ${r.scheduled_date
          ? `<div style="font-size:10px;color:var(--accent);margin-top:5px;">📅 ${new Date(r.scheduled_date).toLocaleDateString('uk-UA')} · ${WINDOWS[r.arrival_window]||''}</div>`
          : `<div class="rc-dl ${dlClass(days)}" style="margin-top:5px;font-size:10px;">Дедлайн: ${dlLabel(r.deadline_at)}</div>`}
      </div>`;
  }).join('');

  mount.querySelectorAll('.rcard').forEach(c =>
    c.addEventListener('click', () => selectRequest(c.dataset.id))
  );
}

/* ════════════════════════════════════════
   RENDER: DETAIL
════════════════════════════════════════ */
async function selectRequest(id) {
  S.selectedId = id;
  renderQueue();

  const r = S.requests.find(x => x.id === id);
  if (!r) return;
  const b = S.buildings.find(x => x.id === r.building_id);
  const connector = r.assigned_user_id
    ? S.connectors.find(c => c.id === r.assigned_user_id)
    : null;

  el('dHead').style.display = 'flex';
  el('dTitle').textContent  = `${r.customer_name} · кв. ${r.flat_number}`;

  // action buttons
  const canSchedule  = ['new','postponed','no_access'].includes(r.status);
  const canPostpone  = ['scheduled','new'].includes(r.status);

  el('dActions').innerHTML = `
    ${canSchedule  ? `<button class="btn sm pri" id="btnSchedule">Призначити виїзд</button>` : ''}
    ${canPostpone  ? `<button class="btn sm warn" id="btnPostpone">↩ Перенести</button>`     : ''}`;

  el('btnSchedule')?.addEventListener('click', () => openSchedule(r));
  el('btnPostpone')?.addEventListener('click', () => openPostpone(r));

  // detail body
  el('dScroll').innerHTML = `
    <div class="dsec">
      <div class="dsec-label">Заявка</div>
      <table class="info-table">
        ${irow('Клієнт',    r.customer_name)}
        ${irow('Телефон',   `<a href="tel:${r.phone}" style="color:var(--accent);text-decoration:none;">${r.phone}</a>`)}
        ${irow('Адреса',    b?.address || '—')}
        ${irow('Квартира',  r.flat_number)}
        ${irow('Дедлайн',   dlLabel(r.deadline_at))}
        ${irow('Статус',    statusPill(r.status))}
        ${r.notes ? irow('Примітка', r.notes) : ''}
      </table>
    </div>

    <div class="dsec">
      <div class="dsec-label">Призначення</div>
      <div class="schedule-box">
        <div class="sb-row" style="margin-bottom:6px;">
          <span class="sb-label">Дата:</span>
          ${r.scheduled_date
            ? `<span class="sb-val">${new Date(r.scheduled_date).toLocaleDateString('uk-UA',{weekday:'short',day:'numeric',month:'long'})}</span>`
            : `<span class="sb-val missing">не призначено</span>`}
        </div>
        <div class="sb-row" style="margin-bottom:6px;">
          <span class="sb-label">Вікно:</span>
          <span class="sb-val">${WINDOWS[r.arrival_window] || '—'}</span>
        </div>
        <div class="sb-row">
          <span class="sb-label">Монтажник:</span>
          ${connector
            ? `<span class="sb-val" style="color:var(--green);">✓ ${connector.name}</span>`
            : `<span class="sb-val missing">не призначено</span>`}
        </div>
      </div>
    </div>

    <div class="dsec">
      <div class="dsec-label">Контакти</div>
      <div id="req-contacts-mount"></div>
    </div>

    <div class="dsec">
      <div class="dsec-label">Нотатки</div>
      <div id="req-notes-mount"></div>
    </div>`;

  // load widgets
  new FiberWidgets.ContactsWidget('req-contacts-mount', { context:'request', id:r.id }).load();
  new FiberWidgets.NotesWidget('req-notes-mount', {
    context:'request', id:r.id,
    allowedTypes:['note','access_note','warning','postpone'],
  }).load();
}

function irow(label, value) {
  return `<tr><td>${label}</td><td>${value}</td></tr>`;
}

/* ════════════════════════════════════════
   RENDER: CONNECTORS PANEL
════════════════════════════════════════ */
function renderConnectors() {
  const mount = el('connectorList');
  if (!S.connectors.length) {
    mount.innerHTML = `<div style="color:var(--muted);font-size:11px;">Монтажників не знайдено</div>`;
    return;
  }

  mount.innerHTML = S.connectors.map(c => {
    const todayCount = S.requests.filter(r =>
      r.assigned_user_id === c.id && r.scheduled_date && isToday(r.scheduled_date)
    ).length;
    const initials = c.name.split(' ').map(w=>w[0]).join('').slice(0,2).toUpperCase();

    return `
      <div class="connector-chip">
        <div class="cc-avatar">${initials}</div>
        <div class="cc-name">${c.name}</div>
        <div class="cc-load">${todayCount} сьогодні</div>
      </div>`;
  }).join('');

  // populate schedule modal select
  const sel = el('schedConnector');
  sel.innerHTML = '<option value="">— оберіть монтажника —</option>' +
    S.connectors.map(c => {
      const load = S.requests.filter(r => r.assigned_user_id === c.id && !['completed','canceled'].includes(r.status)).length;
      return `<option value="${c.id}">${c.name} · ${c.phone} (${load} активних)</option>`;
    }).join('');
}

/* ════════════════════════════════════════
   RENDER: KPI
════════════════════════════════════════ */
function renderKpi() {
  const today     = S.requests.filter(r => r.scheduled_date && isToday(r.scheduled_date)).length;
  const doneToday = S.requests.filter(r => r.status==='completed' && r.completed_at && isToday(r.completed_at)).length;
  const newReqs   = S.requests.filter(r => r.status==='new').length;
  const overdue   = S.requests.filter(r => !['completed','canceled'].includes(r.status) && dlDays(r.deadline_at) < 0).length;

  el('kToday').textContent    = today;
  el('kDoneToday').textContent = doneToday;
  el('kNew').textContent      = newReqs;
  el('kOver').textContent     = overdue;
}

/* ════════════════════════════════════════
   MODAL: SCHEDULE
════════════════════════════════════════ */
function openSchedule(r) {
  S.schedulingId = r.id;
  el('schedModalSub').textContent = `${r.customer_name} · кв. ${r.flat_number}`;
  el('schedDate').value   = r.scheduled_date || '';
  el('schedWindow').value = r.arrival_window || 'before_lunch';
  el('schedConnector').value = r.assigned_user_id || '';
  el('schedWarn').style.display = 'none';
  el('scheduleModal').classList.add('open');
}
el('closeSchedule').addEventListener('click', () => el('scheduleModal').classList.remove('open'));

el('confirmSchedule').addEventListener('click', async () => {
  const date      = el('schedDate').value;
  const window_   = el('schedWindow').value;
  const connector = el('schedConnector').value;

  if (!date || !connector) {
    el('schedWarn').textContent = 'Заповніть дату та оберіть монтажника';
    el('schedWarn').style.display = 'block';
    return;
  }

  const btn = el('confirmSchedule');
  btn.disabled = true;
  try {
    await api(`/api/subscriber-requests/${S.schedulingId}/schedule`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scheduled_date:   date,
        arrival_window:   window_,
        assigned_user_id: connector,
      }),
    });
    el('scheduleModal').classList.remove('open');
    await loadAll();
    await selectRequest(S.schedulingId);
  } catch(e) {
    el('schedWarn').textContent = `Помилка: ${e.message}`;
    el('schedWarn').style.display = 'block';
    console.error(e);
  } finally { btn.disabled = false; }
});

/* ════════════════════════════════════════
   MODAL: POSTPONE
════════════════════════════════════════ */
function openPostpone(r) {
  S.postponingId = r.id;
  el('postponeReason').value = '';
  el('postponeModal').classList.add('open');
}
el('closePostpone').addEventListener('click', () => el('postponeModal').classList.remove('open'));

el('confirmPostpone').addEventListener('click', async () => {
  const reason = el('postponeReason').value.trim();
  if (!reason) { el('postponeReason').focus(); return; }

  const btn = el('confirmPostpone');
  btn.disabled = true;
  try {
    await api(`/api/subscriber-requests/${S.postponingId}/postpone`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason }),
    });
    el('postponeModal').classList.remove('open');
    await loadAll();
    await selectRequest(S.postponingId);
  } catch(e) {
    console.error(e);
  } finally { btn.disabled = false; }
});

/* close on backdrop */
document.querySelectorAll('.modal-overlay').forEach(o =>
  o.addEventListener('click', e => { if (e.target===o) o.classList.remove('open'); })
);

/* ════════════════════════════════════════
   FILTERS
════════════════════════════════════════ */
el('fStatus').addEventListener('change', renderQueue);
el('fDate').addEventListener('change', renderQueue);
el('btnRefresh').addEventListener('click', () => loadAll().catch(console.error));

/* ════════════════════════════════════════
   SOCKET
════════════════════════════════════════ */
function initSocket() {
  const token = localStorage.getItem('fiberops_token');
  if (!window.io || !token) return;
  const socket = window.io({ auth:{token}, transports:['websocket','polling'] });
  socket.on('connect',    () => el('socketDot').className = 'sdot on');
  socket.on('disconnect', () => el('socketDot').className = 'sdot');
  socket.on('subscriber_request.update', () => loadAll().catch(console.error));
}

/* ════════════════════════════════════════
   DATA
════════════════════════════════════════ */
async function loadAll() {
  const [requests, buildings, workers] = await Promise.all([
    api('/api/subscriber-requests'),
    api('/api/buildings'),
    api('/api/field/workers'),
  ]);
  S.requests  = requests  || [];
  S.buildings = buildings || [];

  // connectors only — role must match
  S.connectors = (workers || []).filter(w => {
    const roles = w.roles || [w.role];
    return roles.includes('Connector');
  });

  renderQueue();
  renderKpi();
  renderConnectors();
}

/* ════════════════════════════════════════
   BOOT
════════════════════════════════════════ */
async function boot() {
  try {
    await FiberAuth.requireAuth({ roles: ['ConnectionDispatcher', 'Dispatcher'] });
    FiberAuth.bindUserBar();
  } catch(e) {
    if (e.message === 'forbidden-role') {
      window.location.href = FiberAuth.routeForRoles(FiberAuth.getStoredUser());
      return;
    }
    throw e;
  }
  await loadAll().catch(e => {
    if (e.status === 401) window.location.href = '/login?next=%2Fconnections-dispatch';
  });
  initSocket();
  setInterval(() => loadAll().catch(console.error), 30_000);
}

boot().catch(console.error);
