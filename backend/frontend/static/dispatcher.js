'use strict';

const state = {
  tasks: [],
  brigades: [],
  timeline: [],
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
  completed: 'Завершено',
  canceled: 'Скасовано',
};

function el(id) {
  return document.getElementById(id);
}

async function readJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status} ${url} ${text}`);
  }
  return response.json();
}

function renderTasks() {
  const mount = el('tasksList');
  if (!state.tasks.length) {
    mount.innerHTML = '<p class="placeholder">Задач поки немає</p>';
    return;
  }
  mount.innerHTML = state.tasks.map((task) => {
    const hasBrigade = Boolean(task.brigade_name);
    return `
      <article class="item">
        <div class="row">
          <p class="title">${icons[task.type] || '•'} ${task.building_address || 'Без адреси'}</p>
          <span class="tag ${task.status}">${statusLabel[task.status] || task.status}</span>
        </div>
        <p class="sub">${task.description || 'Опис не вказаний'}</p>
        <p class="sub">Бригада: ${task.brigade_name || 'не призначена'} · ${task.estimated_hours || 0} год</p>
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
        await readJson(`/api/tasks/${taskId}/assign`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ brigade_id: pick.value }),
        });
        await loadAll();
      } catch (err) {
        console.error(err);
        btn.disabled = false;
      }
    });
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
    <article class="item">
      <div class="row">
        <p class="title">${icons[brigade.type] || '•'} ${brigade.name}</p>
        <span class="tag ${brigade.is_active ? 'in_progress' : 'canceled'}">${brigade.status_label}</span>
      </div>
      <p class="sub">Учасники: ${brigade.members}</p>
      <p class="sub">Задачі: ${brigade.tasks.length}</p>
    </article>
  `).join('');
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

async function loadAll() {
  const [tasks, brigades, timeline] = await Promise.all([
    readJson('/api/tasks'),
    readJson('/api/brigades'),
    readJson('/api/timeline'),
  ]);
  state.tasks = tasks;
  state.brigades = brigades;
  state.timeline = timeline;
  renderTasks();
  renderBrigades();
  renderTimeline();
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
    state.tasks = Array.isArray(payload) ? payload : state.tasks;
    renderTasks();
  });

  socket.on('brigade_board.update', (payload) => {
    state.brigades = Array.isArray(payload) ? payload : state.brigades;
    renderBrigades();
  });
}

async function boot() {
  el('refreshTasks').addEventListener('click', () => loadAll().catch(console.error));
  try {
    await loadAll();
  } catch (err) {
    console.error(err);
    el('tasksList').innerHTML = '<p class="placeholder">Не вдалося завантажити /api/tasks</p>';
    el('brigadesList').innerHTML = '<p class="placeholder">Не вдалося завантажити /api/brigades</p>';
    el('timelineList').innerHTML = '<p class="placeholder">Не вдалося завантажити /api/timeline</p>';
  }
  setInterval(() => loadAll().catch(console.error), 30000);
  initSocket();
}

boot();
