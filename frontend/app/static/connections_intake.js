'use strict';
/* ═══════════════════════════════════════════════
   connections_intake.js
   Менеджер вводить заявки клієнтів на підключення.
   Доступ: Dispatcher | Designer (тимчасово, до появи ролі Manager)
═══════════════════════════════════════════════ */

const S = {
  buildings: [],
  requests:  [],
  selectedBuildingId: null,
};

const el = id => document.getElementById(id);
const api = (url, opts) => FiberAuth.fetchJson(url, opts);

/* ─── DEADLINE HELPERS ─── */
function dlDays(str) {
  if (!str) return null;
  return Math.ceil((new Date(str) - new Date()) / 86400000);
}
function dlClass(days) {
  if (days === null) return 'dl-ok';
  if (days < 0)     return 'dl-over';
  if (days <= 7)    return 'dl-soon';
  return 'dl-ok';
}
function dlLabel(str) {
  const days = dlDays(str);
  if (days === null) return '—';
  const d = new Date(str).toLocaleDateString('uk-UA', { day:'numeric', month:'short' });
  if (days < 0)  return `⚠ ${Math.abs(days)} дн. тому · ${d}`;
  if (days === 0) return `Сьогодні · ${d}`;
  if (days <= 7)  return `${days} дн. · ${d}`;
  return d;
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
    canceled:       ['s-canceled', '—', 'Скасовано'],
    technical_issue:['s-no_access','⚠', 'Тех. проблема'],
  };
  const [cls, , label] = map[status] || ['s-new', '○', status];
  return `<span class="spill ${cls}"><span class="spill-dot"></span>${label}</span>`;
}

/* ════════════════════════════════════════
   BUILDING SEARCH
════════════════════════════════════════ */
const bSearch = el('buildingSearch');
const bResults = el('buildingResults');
const bSelected = el('buildingSelected');

bSearch.addEventListener('input', () => {
  const q = bSearch.value.trim().toLowerCase();
  if (q.length < 2) { bResults.style.display = 'none'; return; }

  const matches = S.buildings.filter(b =>
    b.address.toLowerCase().includes(q) ||
    (b.city || '').toLowerCase().includes(q)
  ).slice(0, 8);

  if (!matches.length) { bResults.style.display = 'none'; return; }

  bResults.innerHTML = matches.map(b => {
    const flats = (b.entrances_count||0) * (b.floors_count||0) * (b.flats_per_floor||0);
    return `
      <div class="building-opt" data-id="${b.id}">
        <div class="b-addr">${b.address}</div>
        <div class="b-meta">${b.city||''} · ${flats} кв. · ${b.entrances_count||0} під.</div>
      </div>`;
  }).join('');
  bResults.style.display = 'block';

  bResults.querySelectorAll('.building-opt').forEach(opt => {
    opt.addEventListener('click', () => selectBuilding(opt.dataset.id));
  });
});

function selectBuilding(id) {
  const b = S.buildings.find(x => x.id === id);
  if (!b) return;
  S.selectedBuildingId = id;
  bSearch.value = '';
  bResults.style.display = 'none';

  const flats = (b.entrances_count||0) * (b.floors_count||0) * (b.flats_per_floor||0);
  el('bsAddr').textContent = b.address;
  el('bsMeta').textContent = `${b.city||''} · ${flats} кв. · ${b.entrances_count||0} під.`;
  bSelected.style.display = 'block';
  bSearch.style.display = 'none';
}

el('bsClear').addEventListener('click', () => {
  S.selectedBuildingId = null;
  bSelected.style.display = 'none';
  bSearch.style.display = 'block';
  bSearch.value = '';
  bSearch.focus();
});

// close dropdown on outside click
document.addEventListener('click', e => {
  if (!bSearch.contains(e.target) && !bResults.contains(e.target)) {
    bResults.style.display = 'none';
  }
});

/* ════════════════════════════════════════
   FORM SUBMIT
════════════════════════════════════════ */
function clearForm() {
  S.selectedBuildingId = null;
  bSearch.value = '';
  bSearch.style.display = 'block';
  bSelected.style.display = 'none';
  bResults.style.display = 'none';
  el('flatNumber').value    = '';
  el('customerName').value  = '';
  el('customerPhone').value = '';
  el('requestNotes').value  = '';
  el('deadlineAt').value    = '';
  el('formError').style.display = 'none';
}

el('btnClearForm').addEventListener('click', clearForm);

el('btnSubmit').addEventListener('click', async () => {
  const errEl = el('formError');
  errEl.style.display = 'none';

  const building_id    = S.selectedBuildingId;
  const flat_number    = parseInt(el('flatNumber').value);
  const customer_name  = el('customerName').value.trim();
  const phone          = el('customerPhone').value.trim();
  const notes          = el('requestNotes').value.trim();
  const deadline_at    = el('deadlineAt').value;

  // validation
  const errors = [];
  if (!building_id)                 errors.push('Виберіть будинок');
  if (!flat_number || flat_number < 1) errors.push('Введіть номер квартири');
  if (!customer_name)               errors.push('Введіть ім\'я клієнта');
  if (!phone)                       errors.push('Введіть телефон');
  if (!deadline_at)                 errors.push('Вкажіть дедлайн');

  if (errors.length) {
    errEl.textContent = errors.join(' · ');
    errEl.style.display = 'block';
    return;
  }

  const btn = el('btnSubmit');
  btn.disabled = true;
  try {
    await api('/api/subscriber-requests', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        building_id,
        flat_number,
        customer_name,
        phone,
        notes:       notes || undefined,
        deadline_at: deadline_at ? new Date(deadline_at).toISOString() : undefined,
      }),
    });
    clearForm();
    await loadRequests();
  } catch(e) {
    errEl.textContent = `Помилка: ${e.message || 'спробуйте ще раз'}`;
    errEl.style.display = 'block';
    console.error(e);
  } finally {
    btn.disabled = false;
  }
});

/* ════════════════════════════════════════
   RENDER: REQUEST LIST
════════════════════════════════════════ */
function filteredRequests() {
  const q      = el('fSearch').value.trim().toLowerCase();
  const status = el('fStatus').value;
  return S.requests.filter(r => {
    if (status && r.status !== status) return false;
    if (q) {
      const hay = `${r.customer_name} ${r.phone} ${r.building_address||''}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

function renderRequests() {
  const list = filteredRequests();
  el('listCount').textContent = list.length;
  const mount = el('requestList');

  if (!list.length) {
    mount.innerHTML = `<div class="empty"><div class="empty-icon">◉</div><span>Заявок немає</span></div>`;
    return;
  }

  mount.innerHTML = `
    <table class="rtable">
      <thead>
        <tr>
          <th>Клієнт</th>
          <th>Адреса · Кв.</th>
          <th>Телефон</th>
          <th>Дедлайн</th>
          <th>Статус</th>
        </tr>
      </thead>
      <tbody>
        ${list.map(r => {
          const days = dlDays(r.deadline_at);
          const b = S.buildings.find(b => b.id === r.building_id);
          return `
            <tr data-id="${r.id}">
              <td><div class="req-name">${r.customer_name}</div></td>
              <td>
                <div class="req-addr">${b?.address || '—'}</div>
                <div class="req-flat">кв. ${r.flat_number}</div>
              </td>
              <td><div class="req-phone">${r.phone}</div></td>
              <td><div class="req-dl ${dlClass(days)}">${dlLabel(r.deadline_at)}</div></td>
              <td>${statusPill(r.status)}</td>
            </tr>`;
        }).join('')}
      </tbody>
    </table>`;

  mount.querySelectorAll('tr[data-id]').forEach(row => {
    row.addEventListener('click', () => openDetail(row.dataset.id));
  });
}

/* ════════════════════════════════════════
   RENDER: KPI
════════════════════════════════════════ */
function renderKpi() {
  const now = new Date();
  const thisMonth = r =>
    r.completed_at && new Date(r.completed_at).getMonth() === now.getMonth();

  el('kTotal').textContent = S.requests.length;
  el('kNew').textContent   = S.requests.filter(r => r.status === 'new').length;
  el('kDone').textContent  = S.requests.filter(r => r.status === 'completed' && thisMonth(r)).length;
  el('kOver').textContent  = S.requests.filter(r =>
    !['completed','canceled'].includes(r.status) && dlDays(r.deadline_at) < 0
  ).length;
}

/* ════════════════════════════════════════
   DETAIL MODAL
════════════════════════════════════════ */
function openDetail(id) {
  const r = S.requests.find(x => x.id === id);
  if (!r) return;
  const b = S.buildings.find(x => x.id === r.building_id);

  el('detailModalTitle').textContent = `${r.customer_name} · кв. ${r.flat_number}`;

  el('detailModalBody').innerHTML = `
    <table style="width:100%;border-collapse:collapse;margin-bottom:16px;">
      ${drow('Адреса', b?.address || '—')}
      ${drow('Квартира', r.flat_number)}
      ${drow('Телефон', `<a href="tel:${r.phone}" style="color:var(--accent);text-decoration:none;">${r.phone}</a>`)}
      ${drow('Дедлайн', dlLabel(r.deadline_at))}
      ${drow('Статус', statusPill(r.status))}
      ${r.notes ? drow('Примітка', r.notes) : ''}
      ${drow('Зареєстровано', new Date(r.registered_at).toLocaleDateString('uk-UA'))}
    </table>
    <div id="detail-contacts-mount" style="margin-bottom:16px;"></div>
    <div id="detail-notes-mount"></div>`;

  // mount shared widgets
  const contacts = new FiberWidgets.ContactsWidget('detail-contacts-mount', {
    context: 'request', id: r.id,
  });
  contacts.load();

  const notes = new FiberWidgets.NotesWidget('detail-notes-mount', {
    context: 'request', id: r.id,
    allowedTypes: ['note', 'access_note', 'warning', 'postpone'],
  });
  notes.load();

  el('detailModal').classList.add('open');
}

function drow(label, value) {
  return `<tr>
    <td style="padding:5px 0;color:var(--muted);font-size:11px;width:110px;vertical-align:top;">${label}</td>
    <td style="padding:5px 0;font-size:12px;">${value}</td>
  </tr>`;
}

el('closeDetail').addEventListener('click', () => el('detailModal').classList.remove('open'));
el('detailModal').addEventListener('click', e => { if (e.target === el('detailModal')) el('detailModal').classList.remove('open'); });

/* ════════════════════════════════════════
   FILTERS
════════════════════════════════════════ */
el('fSearch').addEventListener('input', renderRequests);
el('fStatus').addEventListener('change', renderRequests);
el('btnRefresh').addEventListener('click', () => loadAll().catch(console.error));

/* ════════════════════════════════════════
   DATA
════════════════════════════════════════ */
async function loadRequests() {
  S.requests = await api('/api/subscriber-requests') || [];
  renderRequests();
  renderKpi();
}

async function loadAll() {
  const [buildings, requests] = await Promise.all([
    api('/api/buildings'),
    api('/api/subscriber-requests'),
  ]);
  S.buildings = buildings || [];
  S.requests  = requests  || [];
  renderRequests();
  renderKpi();
}

/* ════════════════════════════════════════
   BOOT
════════════════════════════════════════ */
async function boot() {
  try {
    await FiberAuth.requireAuth({ roles: ['Dispatcher', 'Designer'] });
    FiberAuth.bindUserBar();
  } catch(e) {
    if (e.message === 'forbidden-role') {
      window.location.href = FiberAuth.routeForRoles(FiberAuth.getStoredUser());
      return;
    }
    throw e;
  }
  await loadAll().catch(e => {
    if (e.status === 401) window.location.href = '/login?next=%2Fconnections-intake';
  });
  setInterval(() => loadAll().catch(console.error), 60_000);
}

boot().catch(console.error);
