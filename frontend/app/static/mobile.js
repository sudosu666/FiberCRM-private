(function () {
  'use strict';

  const S = {
    tasks: [],
    activeTask: null,
    steps: [],
    socket: null
  };

  const el = (id) => document.getElementById(id);

  async function api(url, opts) {
    return FiberAuth.fetchJson(url, opts || {});
  }

  function renderTasks() {
    const root = el('taskList');
    if (!root) return;
    if (!S.tasks.length) {
      root.innerHTML = '<div class="placeholder">Задачі не знайдено</div>';
      return;
    }
    root.innerHTML = S.tasks.map((task) => (
      '<button class="task-card" data-task="' + task.id + '" style="text-align:left;background:transparent;color:inherit;cursor:pointer">' +
      '<div style="font-weight:600">' + (task.building_address || 'Без адреси') + '</div>' +
      '<div class="secondary">' + (task.description || 'Без опису') + '</div>' +
      '<div class="secondary">Статус: ' + task.status + '</div>' +
      '</button>'
    )).join('');

    root.querySelectorAll('[data-task]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const id = btn.getAttribute('data-task');
        S.activeTask = S.tasks.find((t) => t.id === id) || null;
        renderStatusMeta();
        loadSteps().catch(console.error);
      });
    });

    if (!S.activeTask) S.activeTask = S.tasks[0];
    renderStatusMeta();
  }

  function renderStatusMeta() {
    const node = el('taskStatusMeta');
    if (!node) return;
    if (!S.activeTask) {
      node.textContent = 'Статус: немає активної задачі';
      return;
    }
    node.textContent = 'Статус: ' + S.activeTask.status + ' · task ' + String(S.activeTask.id).slice(0, 8);
  }

  function renderSteps() {
    const root = el('stepTimeline');
    if (!root) return;
    if (!S.steps.length) {
      root.innerHTML = '<div class="placeholder">Кроки не знайдено</div>';
      el('stepBadge').textContent = 'Кроків: 0';
      return;
    }

    const done = S.steps.filter((s) => s.is_done).length;
    el('stepBadge').textContent = 'Кроків: ' + done + '/' + S.steps.length;
    root.innerHTML = S.steps.map((step) => (
      '<div class="step-card">' +
      '<div style="font-weight:600">' + step.step_order + '. ' + step.title + '</div>' +
      '<div class="secondary">' + (step.hint || '') + '</div>' +
      '<div class="secondary">Статус: ' + (step.is_done ? 'виконано' : 'в очікуванні') + '</div>' +
      '</div>'
    )).join('');
  }

  function renderPhotos(files) {
    const root = el('photoGrid');
    if (!root) return;
    if (!files.length) {
      root.innerHTML = '<div class="placeholder">Фото ще немає</div>';
      return;
    }
    root.innerHTML = files.map((file) => (
      '<div class="photo-card">' + file.name + '</div>'
    )).join('');
  }

  function appendChat(role, text) {
    const root = el('chatWindow');
    if (!root) return;
    const row = document.createElement('div');
    row.className = 'chat-msg';
    row.innerHTML = '<strong>' + role + ':</strong> ' + text;
    root.appendChild(row);
    root.scrollTop = root.scrollHeight;
  }

  async function loadTasks() {
    S.tasks = await api('/api/tasks');
    renderTasks();
  }

  async function loadSteps() {
    if (!S.activeTask) return;
    S.steps = await api('/api/tasks/' + S.activeTask.id + '/steps');
    renderSteps();
  }

  async function patchTask(path, payload) {
    if (!S.activeTask) return;
    await api('/api/tasks/' + S.activeTask.id + path, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload || {})
    });
    await loadTasks();
  }

  function bindTabs() {
    document.querySelectorAll('.phase-tab').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.phase-tab').forEach((tab) => tab.classList.remove('is-active'));
        btn.classList.add('is-active');
        const target = btn.getAttribute('data-target');
        document.querySelectorAll('.panel').forEach((panel) => {
          panel.style.display = panel.id === target ? '' : 'none';
        });
      });
    });
    document.querySelectorAll('.panel').forEach((panel, idx) => {
      panel.style.display = idx === 0 ? '' : 'none';
    });
  }

  function bindActions() {
    el('refreshTasks')?.addEventListener('click', () => {
      loadTasks().then(loadSteps).catch(console.error);
    });
    el('startTask')?.addEventListener('click', () => patchTask('/start').catch(console.error));
    el('finishTask')?.addEventListener('click', () => patchTask('/finish').catch(console.error));
    el('holdTask')?.addEventListener('click', () => {
      patchTask('/hold', {
        reason: el('holdReason')?.value || 'pause',
        is_critical: Boolean(el('holdCritical')?.checked)
      }).catch(console.error);
    });
    el('postponeTask')?.addEventListener('click', () => {
      patchTask('/postpone', { reason: el('postponeReason')?.value || 'postpone' }).catch(console.error);
    });
    el('advanceStep')?.addEventListener('click', async () => {
      if (!S.activeTask) return;
      const pending = (S.steps || []).find((s) => !s.is_done);
      if (!pending) return;
      await api('/api/tasks/' + S.activeTask.id + '/steps/' + pending.id + '/complete', { method: 'PATCH' });
      await loadSteps();
    });

    el('addPhotoButton')?.addEventListener('click', () => el('photoInput')?.click());
    el('photoInput')?.addEventListener('change', (e) => {
      const files = Array.from((e.target && e.target.files) || []);
      renderPhotos(files);
    });

    el('chatForm')?.addEventListener('submit', (e) => {
      e.preventDefault();
      const input = el('chatInput');
      const text = (input?.value || '').trim();
      if (!text) return;
      appendChat('Я', text);
      if (input) input.value = '';
      if (S.socket) {
        S.socket.emit('chat.message', { body: text, room: 'dispatchers' });
      }
    });
  }

  function bindSocket() {
    if (!window.io) return;
    const token = FiberAuth.getStoredToken();
    if (!token) return;
    const socket = window.io({ auth: { token }, transports: ['websocket', 'polling'] });
    S.socket = socket;
    socket.on('connect', () => {
      el('chatStatus').textContent = 'online';
      el('signalStrength').textContent = '🛰️ Online';
    });
    socket.on('disconnect', () => {
      el('chatStatus').textContent = 'offline';
      el('signalStrength').textContent = '🛰️ Offline';
    });
    socket.on('chat.message', (payload) => appendChat(payload?.author_name || 'Диспетчер', payload?.body || ''));
  }

  async function boot() {
    try {
      await FiberAuth.requireAuth({ roles: ['Builder', 'Welder', 'Connector'] });
      FiberAuth.bindUserBar();
    } catch (err) {
      if (err && err.message === 'forbidden-role') {
        window.location.href = FiberAuth.routeForRoles(FiberAuth.getStoredUser());
        return;
      }
      window.location.href = '/login?next=%2Ffield';
      return;
    }

    bindTabs();
    bindActions();
    bindSocket();
    el('syncStatus').textContent = 'Синхронізація: online';
    await loadTasks();
    await loadSteps();
  }

  boot().catch(console.error);
})();
