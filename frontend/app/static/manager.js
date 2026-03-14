'use strict';
/* ═══════════════════════════════════════════════
   Менеджер — керівний дашборд
   Доступ: Designer | Dispatcher (тимчасово, поки немає ролі Manager в БД)

   Що робить:
   1. Заводить тендери
   2. Відстежує дедлайни
   3. Затверджує план архітектора → після цього доступно диспетчеру
   4. KPI по кожному тендеру
═══════════════════════════════════════════════ */

const S = {
  tenders:    [],
  buildings:  [],  // all buildings (filtered per tender in render)
  tasks:      [],
  selectedId: null,
  approvingBuildingId: null,
};

const el = id => document.getElementById(id);

async function api(url, opts = {}) {
  return FiberAuth.fetchJson(url, opts);
}

/* ─── DEADLINE UTILS ─── */
function deadlineDays(dateStr) {
  if (!dateStr) return null;
  const diff = new Date(dateStr) - new Date();
  return Math.ceil(diff / 86400000);
}

function deadlineClass(days) {
  if (days === null) return 'dl-none';
  if (days < 0)   return 'dl-overdue';
  if (days <= 14) return 'dl-soon';
  return 'dl-ok';
}

function deadlineLabel(days, dateStr) {
  if (days === null) return 'Без дедлайну';
  const d = new Date(dateStr).toLocaleDateString('uk-UA', { day:'numeric', month:'short' });
  if (days < 0)  return `⚠ Прострочено ${Math.abs(days)} дн. · ${d}`;
  if (days === 0) return `⚠ Сьогодні · ${d}`;
  if (days <= 14) return `${days} дн. · ${d}`;
  return d;
}

/* ─── STATUS PILL ─── */
function statusPill(status) {
  const map = {
    new:         ['p-new',      '○', 'Новий'],
    planning:    ['p-planning', '◎', 'Планування'],
    in_progress: ['p-progress', '●', 'В роботі'],
    completed:   ['p-done',     '✓', 'Завершено'],
  };
  const [cls, , label] = map[status] || ['p-new', '○', status];
  return `<span class="spill ${cls}"><span class="spill-dot"></span>${label}</span>`;
}

/* ─── PLAN APPROVAL STATUS ───
   Поки в БД немає поля "plan_approved", використовуємо proxy:
   - building.infrastructure_status === 'planned' + tasks exist  → "план готовий, чекає затвердження"
   - building.infrastructure_status === 'in_progress'            → "затверджено, в роботі"
   - building.infrastructure_status === 'completed'              → "здано"
   - no tasks                                                     → "не сплановано"
   Коли додамо поле на бек — замінити цю функцію.
─── */
function planStatus(building, buildingTasks) {
  const s = building.infrastructure_status;
  if (s === 'completed')   return { cls: 'pc-ok',   icon: '✓', label: 'Здано' };
  if (s === 'in_progress') return { cls: 'pc-ok',   icon: '✓', label: 'Затверджено' };
  if (buildingTasks.length > 0) return { cls: 'pc-wait', icon: '⏳', label: 'Чекає затвердження' };
  return { cls: 'pc-none', icon: '—',  label: 'Не сплановано' };
}

function needsApproval(building, buildingTasks) {
  return building.infrastructure_status === 'planned' && buildingTasks.length > 0;
}

/* ════════════════════════════════════════
   RENDER: TENDER LIST
════════════════════════════════════════ */
function renderTenders() {
  el('tenderCount').textContent = S.tenders.length;
  const mount = el('tenderList');

  if (!S.tenders.length) {
    mount.innerHTML = `<div class="empty"><div class="empty-icon">◎</div><span>Тендерів немає.<br>Натисніть «+ Тендер»</span></div>`;
    return;
  }

  mount.innerHTML = S.tenders.map(t => {
    const days = deadlineDays(t.deadline);
    const urgency = days !== null && days < 0 ? 'overdue' : days !== null && days <= 14 ? 'soon' : '';
    const sel = t.id === S.selectedId ? 'sel' : '';

    // progress: completed buildings / total buildings
    const tBuildings = S.buildings.filter(b => b.tender_id === t.id);
    const done = tBuildings.filter(b => b.infrastructure_status === 'completed').length;
    const pct = tBuildings.length ? Math.round(done / tBuildings.length * 100) : 0;
    const barColor = pct === 100 ? 'var(--green)' : pct > 50 ? 'var(--accent)' : 'var(--amber)';

    return `
      <div class="tcard ${sel} ${urgency}" data-id="${t.id}">
        <div class="tc-top">
          <div class="tc-name">${t.name}</div>
          ${statusPill(t.status)}
        </div>
        <div class="tc-meta">${t.customer || '—'} · ${t.city || 'місто не вказано'}</div>
        <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
          <span class="tc-deadline ${deadlineClass(days)}">${deadlineLabel(days, t.deadline)}</span>
          <span style="font-family:'IBM Plex Mono',monospace;font-size:10px;color:var(--muted);">${done}/${tBuildings.length}</span>
        </div>
        <div class="mini-bar">
          <div class="mini-fill" style="width:${pct}%;background:${barColor};"></div>
        </div>
      </div>`;
  }).join('');

  mount.querySelectorAll('.tcard').forEach(c => {
    c.addEventListener('click', () => selectTender(c.dataset.id));
  });
}

/* ════════════════════════════════════════
   RENDER: TENDER DETAIL
════════════════════════════════════════ */
function selectTender(id) {
  S.selectedId = id;
  renderTenders();
  renderDetail();
}

function renderDetail() {
  const tender = S.tenders.find(t => t.id === S.selectedId);
  if (!tender) {
    el('noSel').style.display = 'flex';
    el('tenderDetail').style.display = 'none';
    return;
  }
  el('noSel').style.display = 'none';
  el('tenderDetail').style.display = 'flex';

  el('detailName').textContent = tender.name;
  el('detailStatusPill').innerHTML = statusPill(tender.status);

  const buildings = S.buildings.filter(b => b.tender_id === tender.id);

  // KPI
  const planned   = buildings.filter(b => b.infrastructure_status !== 'planned' || S.tasks.some(t => t.building_id === b.id)).length;
  const waitApprove = buildings.filter(b => needsApproval(b, S.tasks.filter(t => t.building_id === b.id))).length;
  const done      = buildings.filter(b => b.infrastructure_status === 'completed').length;
  const crit      = S.tasks.filter(t =>
    buildings.some(b => b.id === t.building_id) && t.is_critical && t.status !== 'completed'
  ).length;

  el('kBuildings').textContent  = buildings.length;
  el('kPlanned').textContent    = planned;
  el('kNeedApprove').textContent = waitApprove;
  el('kDone').textContent       = done;
  el('kCrit').textContent       = crit;

  // approve banner
  if (waitApprove > 0) {
    el('approveBanner').style.display = 'flex';
    el('bannerTitle').textContent = `${waitApprove} будинків чекають затвердження плану`;
    el('bannerSub').textContent = 'Архітектор завершив проектування. Перевірте та затвердіть.';
  } else {
    el('approveBanner').style.display = 'none';
  }

  // buildings table
  el('detailBody').innerHTML = buildings.length ? `
    <div class="sec-head">
      <span class="sec-label">Будинки тендера · ${buildings.length} об'єктів</span>
    </div>
    <table class="btable">
      <thead>
        <tr>
          <th>Адреса</th>
          <th>Статус</th>
          <th>Прогрес задач</th>
          <th>План архітектора</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        ${buildings.map(b => buildingRow(b)).join('')}
      </tbody>
    </table>` : `
    <div class="empty" style="height:160px;">
      <div class="empty-icon">▣</div>
      <span>Будинків немає.<br>Архітектор додасть їх після проектування.</span>
    </div>`;

  // bind approve buttons
  el('detailBody').querySelectorAll('[data-approve]').forEach(btn => {
    btn.addEventListener('click', () => openApprove(btn.dataset.approve, btn.dataset.addr));
  });
}

function buildingRow(b) {
  const bTasks  = S.tasks.filter(t => t.building_id === b.id);
  const total   = bTasks.length;
  const done    = bTasks.filter(t => t.status === 'completed').length;
  const pct     = total ? Math.round(done / total * 100) : 0;
  const barColor = pct === 100 ? 'var(--green)' : 'var(--accent)';

  const ps = planStatus(b, bTasks);
  const infra = b.infrastructure_status || 'planned';

  const infraMap = { planned:'ip-planned', in_progress:'ip-in_progress', completed:'ip-completed' };
  const infraLabel = { planned:'Заплановано', in_progress:'В роботі', completed:'Здано' };

  const canApprove = needsApproval(b, bTasks);
  const totalFlats = (b.entrances_count||0) * (b.floors_count||0) * (b.flats_per_floor||0);

  return `
    <tr>
      <td>
        <div class="b-addr">${b.address}</div>
        <div class="b-sub">${b.city||''} · ${totalFlats} кв. · ${b.entrances_count||0} під.</div>
      </td>
      <td><span class="ip ${infraMap[infra]||'ip-planned'}">${infraLabel[infra]||infra}</span></td>
      <td>
        <div style="display:flex;align-items:center;gap:8px;">
          <div class="pbar"><div class="pbar-fill" style="width:${pct}%;background:${barColor};"></div></div>
          <span style="font-family:'IBM Plex Mono',monospace;font-size:10px;color:var(--muted);">${done}/${total}</span>
        </div>
      </td>
      <td>
        <div class="plan-chip ${ps.cls}">${ps.icon} ${ps.label}</div>
      </td>
      <td>
        ${canApprove
          ? `<button class="btn sm approve" data-approve="${b.id}" data-addr="${b.address}">✓ Затвердити</button>`
          : ''}
      </td>
    </tr>`;
}

/* ════════════════════════════════════════
   RENDER: ALERTS (right panel)
════════════════════════════════════════ */
function renderAlerts() {
  const alerts = [];

  S.tenders.forEach(t => {
    const days = deadlineDays(t.deadline);
    if (days === null) return;
    if (days < 0) {
      alerts.push({ cls: 'ai-red',   title: `⚠ Прострочено: ${t.name}`, sub: `${Math.abs(days)} дн. назад` });
    } else if (days <= 7) {
      alerts.push({ cls: 'ai-red',   title: `${t.name}`, sub: `Дедлайн через ${days} дн.` });
    } else if (days <= 14) {
      alerts.push({ cls: 'ai-amber', title: `${t.name}`, sub: `Дедлайн через ${days} дн.` });
    }
  });

  // plans waiting for approval
  const waitTotal = S.buildings.filter(b =>
    needsApproval(b, S.tasks.filter(t => t.building_id === b.id))
  ).length;
  if (waitTotal > 0) {
    alerts.push({ cls: 'ai-amber', title: `${waitTotal} планів чекають затвердження`, sub: 'Архітектор завершив роботу' });
  }

  // critical tasks
  const critTotal = S.tasks.filter(t => t.is_critical && t.status !== 'completed').length;
  if (critTotal > 0) {
    alerts.push({ cls: 'ai-red', title: `${critTotal} критичних задач`, sub: 'Потребують уваги диспетчера' });
  }

  el('alertCount').textContent = alerts.length;

  if (!alerts.length) {
    el('alertList').innerHTML = `<div style="color:var(--muted);font-size:11px;">Все гаразд ✓</div>`;
    return;
  }

  el('alertList').innerHTML = alerts.map(a => `
    <div class="alert-item ${a.cls}">
      <div class="ai-title">${a.title}</div>
      <div class="ai-sub">${a.sub}</div>
    </div>`).join('');
}

/* ════════════════════════════════════════
   MODAL: NEW TENDER
════════════════════════════════════════ */
el('btnNewTender').addEventListener('click', () => el('newTenderModal').classList.add('open'));
el('closeNewTender').addEventListener('click', () => el('newTenderModal').classList.remove('open'));

el('confirmNewTender').addEventListener('click', async () => {
  const name     = el('ntName').value.trim();
  const customer = el('ntCustomer').value.trim();
  const city     = el('ntCity').value.trim();
  const deadline = el('ntDeadline').value;
  if (!name) { el('ntName').focus(); return; }

  const btn = el('confirmNewTender');
  btn.disabled = true;
  try {
    const created = await api('/api/tenders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, customer: customer||undefined, city: city||undefined, deadline: deadline||undefined }),
    });
    el('newTenderModal').classList.remove('open');
    el('ntName').value = ''; el('ntCity').value = ''; el('ntDeadline').value = '';
    await loadAll();
    selectTender(created.id);
  } catch(e) {
    console.error(e);
  } finally { btn.disabled = false; }
});

/* ════════════════════════════════════════
   MODAL: CHANGE STATUS
════════════════════════════════════════ */
el('btnChangeStatus').addEventListener('click', () => {
  if (!S.selectedId) return;
  const t = S.tenders.find(t => t.id === S.selectedId);
  el('newStatusSel').value = t?.status || 'new';
  el('statusModal').classList.add('open');
});
el('closeStatus').addEventListener('click', () => el('statusModal').classList.remove('open'));

el('confirmStatus').addEventListener('click', async () => {
  if (!S.selectedId) return;
  const status = el('newStatusSel').value;
  const btn = el('confirmStatus');
  btn.disabled = true;
  try {
    await api(`/api/tenders/${S.selectedId}/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    });
    el('statusModal').classList.remove('open');
    await loadAll();
    renderDetail();
  } catch(e) {
    console.error(e);
  } finally { btn.disabled = false; }
});

/* ════════════════════════════════════════
   MODAL: APPROVE PLAN
   Воркэраунд поки немає поля plan_approved в БД:
   "Затвердити" = змінити tender.status на in_progress
   + додати comment_type=design_note на будинок
   Коли з'явиться поле на бек — замінити на PATCH /api/buildings/{id}/approve
════════════════════════════════════════ */
function openApprove(buildingId, address) {
  S.approvingBuildingId = buildingId;
  el('approveSubtitle').textContent = address;
  el('approveComment').value = '';
  el('approveModal').classList.add('open');
}

el('closeApprove').addEventListener('click', () => el('approveModal').classList.remove('open'));

el('confirmApprove').addEventListener('click', async () => {
  const bid = S.approvingBuildingId;
  if (!bid) return;

  const comment = el('approveComment').value.trim();
  const body = `Менеджер затвердив план архітектора.${comment ? ' ' + comment : ''}`;

  const btn = el('confirmApprove');
  btn.disabled = true;
  try {
    // Step 1: write approval comment on building
    await api(`/api/buildings/${bid}/comments`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ body, comment_type: 'design_note', role_tags: ['Dispatcher'] }),
    });

    // Step 2: if tender is still in 'planning', move it to 'in_progress'
    if (S.selectedId) {
      const tender = S.tenders.find(t => t.id === S.selectedId);
      if (tender?.status === 'planning' || tender?.status === 'new') {
        await api(`/api/tenders/${S.selectedId}/status`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status: 'in_progress' }),
        });
      }
    }

    el('approveModal').classList.remove('open');
    await loadAll();
    renderDetail();
  } catch(e) {
    console.error(e);
  } finally { btn.disabled = false; }
});

/* close overlays on backdrop click */
document.querySelectorAll('.modal-overlay').forEach(o =>
  o.addEventListener('click', e => { if (e.target === o) o.classList.remove('open'); })
);

/* ════════════════════════════════════════
   DATA
════════════════════════════════════════ */
async function loadAll() {
  const [tenders, buildings, tasks] = await Promise.all([
    api('/api/tenders'),
    api('/api/buildings'),
    api('/api/tasks'),
  ]);
  S.tenders   = tenders   || [];
  S.buildings = buildings || [];
  S.tasks     = tasks     || [];

  renderTenders();
  renderAlerts();
  if (S.selectedId) renderDetail();
}

/* ════════════════════════════════════════
   BOOT
════════════════════════════════════════ */
el('btnRefresh').addEventListener('click', () => loadAll().catch(console.error));

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
    console.error(e);
    if (e.status === 401) window.location.href = '/login?next=%2Fmanager';
  });
  setInterval(() => loadAll().catch(console.error), 60_000);
}

boot().catch(console.error);
