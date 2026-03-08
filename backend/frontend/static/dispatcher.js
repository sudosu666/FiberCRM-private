'use strict';

const state = {
  tasks: [],
  brigades: [],
  timeline: [],
  events: [],
  workers: [],
};

const icons = {
  construction: '🏗',
  welding: '⚡',
  connection: '🔌',
};

const statusLabel = {
  pending: 'Нова',
  assigned: 'Призначено',
  in_progress: 'В роботі',
  on_hold: 'Призупинено',
  completed: 'Завершено',
  canceled: 'Скасовано',
};

function el(id) {
  return document.getElementById(id);
}

async function readJson(url, options) {
  return FiberAuth.fetchJson(url, options || {});
}

function pushEvent(label, ts = new Date().toISOString()) {
  state.events.unshift({ label, ts });
  state.events = state.events.slice(0, 30);
  renderEvents();
}

function unwrapRealtimeItems(payload) {
  if (Array.isArray(payload)) {
    return { items: payload, eventAt: new Date().toISOString() };
  }
  return {
    items: Array.isArray(payload?.items) ? payload.items : [],
    eventAt: payload?.event_at || payload?.timestamp || new Date().toISOString(),
  };
}

async function assignTask(taskId, brigadeId) {
  await readJson(`/api/tasks/${taskId}/assign`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ brigade_id: brigadeId }),
  });
}

async function createGroup(payload) {
  await readJson('/api/brigades', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

function renderTasks() {
  const mount = el('tasksList');
  if (!state.tasks.length) {
    mount.innerHTML = '<p class="placeholder">Задач поки немає</p>';
    return;
  }
  mount.innerHTML = state.tasks.map((task) => {
    const hasBrigade = Boolean(task.brigade_name);
    const itemClass = `${task.is_critical ? 'critical ' : ''}${task.status === 'on_hold' ? 'on_hold' : ''}`.trim();
    return `
      <article class="item ${itemClass}" draggable="true" data-task-id="${task.id}">
        <div class="row">
          <p class="title">${icons[task.type] || '•'} ${task.building_address || 'Без адреси'}</p>
          <span class="tag ${task.status}">${statusLabel[task.status] || task.status}</span>
        </div>
        <p class="sub">${task.description || 'Опис не вказаний'}</p>
        <p class="sub">Бригада: ${task.brigade_name || 'не призначена'} · ${task.estimated_hours || 0} год</p>
        <p class="sub">${task.hold_reason ? `Причина: ${task.hold_reason}` : ''}${task.is_critical ? ' КРИТИЧНО' : ''}</p>
        <div class="assign-row">
          <select id="assign-${task.id}">
            ${state.brigades.map((b) => `<option value="${b.id}">${b.name}</option>`).join('')}
          </select>
          <button type="button" data-task-id="${task.id}" ${hasBrigade ? 'disabled' : ''}>Призначити</button>
        </div>
      </article>
    `;
  }).join('');

  mount.querySelectorAll('button[data-task-id]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const taskId = btn.getAttribute('data-task-id');
      const pick = el(`assign-${taskId}`);
      if (!pick || !pick.value) {
        return;
      }
      btn.disabled = true;
      try {
        await assignTask(taskId, pick.value);
        pushEvent(`Призначення: task ${taskId.slice(0, 8)} -> brigade ${pick.value.slice(0, 8)}`);
        await loadAll();
      } catch (err) {
        console.error(err);
        btn.disabled = false;
      }
    });
  });

  mount.querySelectorAll('.item[draggable="true"]').forEach((card) => {
    card.addEventListener('dragstart', (event) => {
      card.classList.add('dragging');
      event.dataTransfer.setData('text/task-id', card.getAttribute('data-task-id'));
    });
    card.addEventListener('dragend', () => card.classList.remove('dragging'));
  });
}

function renderBrigades() {
  const mount = el('brigadesList');
  el('brigadesCounter').textContent = String(state.brigades.length);
  if (!state.brigades.length) {
    mount.innerHTML = '<p class="placeholder">Бригад поки немає</p>';
    return;
  }
  mount.innerHTML = state.brigades.map((brigade) => `
    <article class="item" data-brigade-id="${brigade.id}">
      <div class="row">
        <p class="title">${icons[brigade.type] || '•'} ${brigade.name}</p>
        <span class="tag ${brigade.is_active ? 'in_progress' : 'canceled'}">${brigade.status_label}</span>
      </div>
      <p class="sub">Учасники: ${brigade.members}</p>
      <p class="sub">Задачі: ${brigade.tasks.length}</p>
      <p class="sub">Drag & Drop: перетягни задачу сюди</p>
    </article>
  `).join('');

  mount.querySelectorAll('.item[data-brigade-id]').forEach((card) => {
    card.addEventListener('dragover', (event) => {
      event.preventDefault();
      card.classList.add('drop-target');
    });
    card.addEventListener('dragleave', () => card.classList.remove('drop-target'));
    card.addEventListener('drop', async (event) => {
      event.preventDefault();
      card.classList.remove('drop-target');
      const taskId = event.dataTransfer.getData('text/task-id');
      const brigadeId = card.getAttribute('data-brigade-id');
      if (!taskId || !brigadeId) {
        return;
      }
      try {
        await assignTask(taskId, brigadeId);
        pushEvent(`DnD: task ${taskId.slice(0, 8)} -> brigade ${brigadeId.slice(0, 8)}`);
        await loadAll();
      } catch (err) {
        console.error(err);
      }
    });
  });
}

function renderWorkersPicker() {
  const foreman = el('groupForeman');
  const members = el('groupMembers');
  if (!foreman || !members) return;
  foreman.innerHTML = '<option value="">Бригадир</option>' + state.workers.map((worker) => (
    `<option value="${worker.id}">${worker.name} · ${worker.roles.join('/')}</option>`
  )).join('');
  members.innerHTML = state.workers.map((worker) => (
    `<option value="${worker.id}">${worker.name}${worker.brigade_name ? ` · ${worker.brigade_name}` : ''}</option>`
  )).join('');
}

function renderTimeline() {
  const mount = el('timelineList');
  if (!state.timeline.length) {
    mount.innerHTML = '<p class="placeholder">Таймлайн поки порожній</p>';
    return;
  }
  mount.innerHTML = state.timeline.map((slot) => {
    const labels = slot.blocks.length
      ? slot.blocks.map((block) => block.label).join(' · ')
      : 'немає задач';
    return `
      <article class="item">
        <div class="row">
          <p class="title">${String(slot.hour).padStart(2, '0')}:00</p>
          <span class="meta">${slot.blocks.length}</span>
        </div>
        <p class="sub">${labels}</p>
      </article>
    `;
  }).join('');
}

function renderEvents() {
  const mount = el('eventFeed');
  if (!state.events.length) {
    mount.innerHTML = '<p class="placeholder">Очікування подій...</p>';
    return;
  }
  mount.innerHTML = state.events.map((entry) => `
    <article class="item">
      <p class="title">${entry.label}</p>
      <p class="sub">${new Date(entry.ts).toLocaleString()}</p>
    </article>
  `).join('');
}

async function loadAll() {
  const [tasks, brigades, timeline, workers] = await Promise.all([
    readJson('/api/tasks'),
    readJson('/api/brigades'),
    readJson('/api/timeline'),
    readJson('/api/field/workers'),
  ]);
  state.tasks = tasks;
  state.brigades = brigades;
  state.timeline = timeline;
  state.workers = workers;
  renderTasks();
  renderBrigades();
  renderTimeline();
  renderWorkersPicker();
  await loadUsers();
}

function roleCheckbox(role, user) {
  const checked = user.roles.includes(role) ? 'checked' : '';
  return `<label class="role-pick"><input type="checkbox" data-role="${role}" ${checked}> ${role}</label>`;
}

function renderUsers(users) {
  const mount = el('usersList');
  if (!mount) return;
  if (!users.length) {
    mount.innerHTML = '<p class="placeholder">Користувачів не знайдено</p>';
    return;
  }
  mount.innerHTML = users.map((user) => `
    <article class="item">
      <div class="row">
        <p class="title">${user.name}</p>
        <span class="tag ${user.is_active ? 'completed' : 'canceled'}">${user.is_active ? 'active' : 'disabled'}</span>
      </div>
      <p class="sub">${user.phone}${user.email ? ` · ${user.email}` : ''}</p>
      <div class="role-editor">
        <select data-user-role="${user.id}">
          ${['Dispatcher', 'Designer', 'Builder', 'Welder', 'Connector', 'Warehouse'].map((role) => `<option value="${role}" ${user.role === role ? 'selected' : ''}>${role}</option>`).join('')}
        </select>
        <label class="role-pick"><input type="checkbox" data-user-active="${user.id}" ${user.is_active ? 'checked' : ''}> active</label>
      </div>
      <div class="roles-grid" data-user-extra="${user.id}">
        ${['Dispatcher', 'Designer', 'Builder', 'Welder', 'Connector', 'Warehouse'].map((role) => roleCheckbox(role, user)).join('')}
      </div>
      <button type="button" data-save-user="${user.id}">Зберегти роль</button>
    </article>
  `).join('');

  mount.querySelectorAll('button[data-save-user]').forEach((button) => {
    button.addEventListener('click', async () => {
      const userId = button.getAttribute('data-save-user');
      const role = mount.querySelector(`[data-user-role="${userId}"]`)?.value;
      const active = mount.querySelector(`[data-user-active="${userId}"]`)?.checked ?? true;
      const additional = Array.from(mount.querySelectorAll(`[data-user-extra="${userId}"] input[data-role]:checked`))
        .map((input) => input.getAttribute('data-role'))
        .filter(Boolean);
      button.disabled = true;
      try {
        await readJson(`/auth/users/${userId}/roles`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ role, additional_roles: additional, is_active: active }),
        });
        pushEvent(`Ролі оновлено для ${userId.slice(0, 8)}`);
        await loadUsers();
      } catch (error) {
        console.error(error);
        button.disabled = false;
      }
    });
  });
}

async function loadUsers() {
  const users = await readJson('/auth/users');
  renderUsers(users);
}

function initSocket() {
  const socketState = el('socketState');
  const token = localStorage.getItem('fiberops_token');
  if (!window.io || !token) {
    socketState.textContent = 'Socket: polling only';
    socketState.className = 'meta warn';
    return;
  }

  const socket = window.io({
    auth: { token },
    transports: ['websocket', 'polling'],
  });

  socket.on('connect', () => {
    socketState.textContent = 'Socket: connected';
    socketState.className = 'meta ok';
  });

  socket.on('connect_error', () => {
    socketState.textContent = 'Socket: auth required';
    socketState.className = 'meta warn';
  });

  socket.on('task_queue.update', (payload) => {
    const { items, eventAt } = unwrapRealtimeItems(payload);
    state.tasks = items.length ? items : state.tasks;
    renderTasks();
    pushEvent('Socket: task_queue.update', eventAt);
  });

  socket.on('brigade_board.update', (payload) => {
    const { items, eventAt } = unwrapRealtimeItems(payload);
    state.brigades = items.length ? items : state.brigades;
    renderBrigades();
    pushEvent('Socket: brigade_board.update', eventAt);
  });

  socket.on('chat.message', (payload) => {
    const msg = payload?.message || 'new chat message';
    pushEvent(`Chat: ${msg}`, payload?.event_at || payload?.timestamp);
  });

  socket.on('progress.update', (payload) => {
    const step = payload?.step || 'step update';
    pushEvent(`Progress: ${step}`, payload?.event_at || payload?.timestamp);
  });

  socket.on('photo.report', (payload) => {
    const who = payload?.brigade_name || 'бригада';
    pushEvent(`Photo: ${who}`, payload?.event_at || payload?.created_at);
  });

  socket.on('task.status', (payload) => {
    pushEvent(`Task status: ${payload?.status || 'unknown'}`, payload?.event_at || payload?.timestamp);
    loadAll().catch(console.error);
  });
}

async function boot() {
  try {
    await FiberAuth.requireAuth({ roles: ['Dispatcher'] });
    FiberAuth.bindUserBar();
  } catch (error) {
    if (error.message === 'forbidden-role') {
      window.location.href = FiberAuth.routeForRoles(FiberAuth.getStoredUser());
      return;
    }
    throw error;
  }
  el('refreshTasks').addEventListener('click', () => loadAll().catch(console.error));
  el('refreshUsers')?.addEventListener('click', () => loadUsers().catch(console.error));
  el('createGroup').addEventListener('click', async () => {
    const name = el('groupName').value.trim();
    const type = el('groupType').value;
    const foremanId = el('groupForeman').value || null;
    const memberIds = Array.from(el('groupMembers').selectedOptions).map((option) => option.value);
    if (!name || !type || memberIds.length === 0) {
      return;
    }
    try {
      await createGroup({
        name,
        type,
        foreman_id: foremanId,
        member_ids: memberIds,
        is_active: true,
      });
      pushEvent(`Група створена: ${name}`);
      el('groupName').value = '';
      await loadAll();
    } catch (error) {
      console.error(error);
    }
  });
  try {
    await loadAll();
  } catch (err) {
    console.error(err);
    if (err.status === 401 || err.status === 403) {
      window.location.href = '/login?next=%2Fdispatcher';
      return;
    }
    el('tasksList').innerHTML = '<p class="placeholder">Не вдалося завантажити /api/tasks</p>';
    el('brigadesList').innerHTML = '<p class="placeholder">Не вдалося завантажити /api/brigades</p>';
    el('timelineList').innerHTML = '<p class="placeholder">Не вдалося завантажити /api/timeline</p>';
    el('usersList').innerHTML = '<p class="placeholder">Не вдалося завантажити /auth/users</p>';
  }
  setInterval(() => loadAll().catch(console.error), 30000);
  initSocket();
}

boot();
