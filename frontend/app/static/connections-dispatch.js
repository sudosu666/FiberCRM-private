'use strict';

const state = {
  buildings: [],
  technicians: [],
  requests: [],
  summary: null,
};

function el(id) {
  return document.getElementById(id);
}

async function readJson(url, options) {
  return FiberAuth.fetchJson(url, options || {});
}

function renderSummary() {
  const mount = el('connectionSummary');
  const summary = state.summary;
  if (!summary) {
    mount.innerHTML = '<p class="placeholder">Немає даних</p>';
    return;
  }
  mount.innerHTML = [
    ['Всього', summary.total_requests],
    ['Нові', summary.new_requests],
    ['Заплановані', summary.scheduled_requests],
    ['Просрочені', summary.overdue_requests],
    ['Без техможливості', summary.technical_blocked],
  ].map(([label, value]) => `
    <article class="stat-card">
      <p class="sub">${label}</p>
      <p class="stat-value">${value}</p>
    </article>
  `).join('');
}

function renderPickers() {
  el('requestBuilding').innerHTML = state.buildings.map((building) => (
    `<option value="${building.building_id}">${building.address} · незатребувано ${building.unclaimed_lines}</option>`
  )).join('');
  el('scheduleRequest').innerHTML = '<option value="">Оберіть заявку</option>' + state.requests
    .filter((item) => item.status === 'new' || item.status === 'postponed')
    .map((item) => (
      `<option value="${item.id}">${item.building_address} · кв. ${item.flat_number} · ${item.customer_name}</option>`
    )).join('');
  el('scheduleUser').innerHTML = state.technicians.map((worker) => (
    `<option value="${worker.id}">${worker.name} · ${worker.phone} · ${worker.role}${worker.brigade_name ? ` · ${worker.brigade_name}` : ''}</option>`
  )).join('');
}

function renderRequests() {
  const mount = el('subscriberRequestsList');
  if (!state.requests.length) {
    mount.innerHTML = '<p class="placeholder">Заявок поки немає</p>';
    return;
  }
  mount.innerHTML = state.requests.map((item) => `
    <article class="item">
      <div class="row">
        <p class="title">${item.building_address} · кв. ${item.flat_number}</p>
        <span class="tag ${item.postponed_over_shift ? 'on_hold' : (item.technical_possible ? 'completed' : 'on_hold')}">${item.status}</span>
      </div>
      <p class="sub">${item.customer_name} · ${item.phone}</p>
      <p class="sub">Зареєстровано ${new Date(item.registered_at).toLocaleDateString()} · дедлайн ${new Date(item.deadline_at).toLocaleDateString()}</p>
      <p class="sub">Лінії: підключено ${item.connected_lines} · резерв ${item.reserved_lines} · незатребувано ${item.unclaimed_lines}</p>
      <p class="sub">${item.technical_possible ? 'Техможливість є' : 'Потрібна добудова або звільнення ресурсу'}</p>
      <p class="sub">${item.assigned_user_name ? `Майстер: ${item.assigned_user_name}` : 'Майстер ще не призначений'}${item.scheduled_date ? ` · ${item.scheduled_date} · ${item.arrival_window}` : ''}</p>
      <p class="sub${item.postponed_over_shift ? ' postpone-alert' : ''}">${item.is_postponed ? `Перенос: ${item.postponed_reason || 'без причини'}${item.postponed_over_shift ? ' · > 1 зміни' : ''}` : ''}</p>
      <p class="sub">${item.notes || ''}</p>
    </article>
  `).join('');
}

async function loadAll() {
  const [buildings, technicians, requests, summary] = await Promise.all([
    readJson('/api/buildings'),
    readJson('/api/field/workers'),
    readJson('/api/subscriber-requests'),
    readJson('/api/subscriber-requests/summary'),
  ]);
  state.buildings = buildings;
  state.technicians = technicians;
  state.requests = requests;
  state.summary = summary;
  renderSummary();
  renderPickers();
  renderRequests();
}

async function createRequest() {
  await readJson('/api/subscriber-requests', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      building_id: el('requestBuilding').value,
      flat_number: Number(el('requestFlat').value),
      customer_name: el('requestCustomer').value.trim(),
      phone: el('requestPhone').value.trim(),
      notes: el('requestNote').value.trim() || null,
    }),
  });
}

async function scheduleRequest() {
  await readJson(`/api/subscriber-requests/${el('scheduleRequest').value}/schedule`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      scheduled_date: el('scheduleDate').value,
      arrival_window: el('scheduleWindow').value,
      assigned_user_id: el('scheduleUser').value,
    }),
  });
}

async function postponeRequest() {
  await readJson(`/api/subscriber-requests/${el('scheduleRequest').value}/postpone`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      reason: el('postponeSubscriberReason').value.trim(),
    }),
  });
}

async function boot() {
  try {
    await FiberAuth.requireAuth({ roles: ['ConnectionDispatcher', 'Dispatcher'] });
    FiberAuth.bindUserBar();
  } catch (error) {
    if (error.message === 'forbidden-role') {
      window.location.href = FiberAuth.routeForRoles(FiberAuth.getStoredUser());
      return;
    }
    throw error;
  }

  el('createSubscriberRequest').addEventListener('click', async () => {
    await createRequest();
    el('requestFlat').value = '';
    el('requestCustomer').value = '';
    el('requestPhone').value = '';
    el('requestNote').value = '';
    await loadAll();
  });

  el('scheduleSubscriberRequest').addEventListener('click', async () => {
    if (!el('scheduleRequest').value || !el('scheduleUser').value || !el('scheduleDate').value) {
      return;
    }
    await scheduleRequest();
    await loadAll();
  });
  el('postponeSubscriberRequest').addEventListener('click', async () => {
    if (!el('scheduleRequest').value || !el('postponeSubscriberReason').value.trim()) {
      return;
    }
    await postponeRequest();
    el('postponeSubscriberReason').value = '';
    await loadAll();
  });

  el('refreshSubscriberRequests').addEventListener('click', () => loadAll().catch(console.error));
  await loadAll();
}

boot().catch(console.error);
