(function () {
  'use strict';

  const state = {
    tasks: [],
    buildings: [],
    brigades: []
  };

  function el(id) {
    return document.getElementById(id);
  }

  async function loadAll() {
    const [tasks, buildings, brigades] = await Promise.all([
      FiberAuth.fetchJson('/api/tasks'),
      FiberAuth.fetchJson('/api/buildings'),
      FiberAuth.fetchJson('/api/brigades')
    ]);
    state.tasks = Array.isArray(tasks) ? tasks : [];
    state.buildings = Array.isArray(buildings) ? buildings : [];
    state.brigades = Array.isArray(brigades) ? brigades : [];
  }

  function statusLabel(status) {
    const labels = {
      pending: 'Очікування',
      assigned: 'Призначено',
      in_progress: 'В роботі',
      completed: 'Виконано',
      canceled: 'Скасовано',
      on_hold: 'Пауза'
    };
    return labels[status] || status || '—';
  }

  function statusColor(status) {
    if (status === 'completed') return 'var(--success)';
    if (status === 'in_progress') return 'var(--accent)';
    if (status === 'assigned') return '#f59e0b';
    if (status === 'canceled') return 'var(--danger)';
    return 'var(--text-secondary)';
  }

  function applyTaskFilters(tasks) {
    const search = (el('filterSearch')?.value || '').trim().toLowerCase();
    const status = el('filterStatus')?.value || '';
    return tasks.filter((task) => {
      if (status && task.status !== status) return false;
      if (!search) return true;
      const address = (task.building_address || '').toLowerCase();
      const brigade = (task.brigade_name || '').toLowerCase();
      const description = (task.description || '').toLowerCase();
      return address.includes(search) || brigade.includes(search) || description.includes(search);
    });
  }

  function renderStats(tasks) {
    const grouped = {
      total: tasks.length,
      pending: tasks.filter((t) => t.status === 'pending').length,
      assigned: tasks.filter((t) => t.status === 'assigned').length,
      in_progress: tasks.filter((t) => t.status === 'in_progress').length,
      completed: tasks.filter((t) => t.status === 'completed').length
    };

    const items = [
      ['Всього', grouped.total, 'var(--accent)'],
      ['Очікують', grouped.pending, 'var(--text-secondary)'],
      ['Призначено', grouped.assigned, '#f59e0b'],
      ['В роботі', grouped.in_progress, 'var(--accent)'],
      ['Виконано', grouped.completed, 'var(--success)']
    ];

    const mount = el('statsCards');
    if (!mount) return;
    mount.innerHTML = items.map(([title, value, color]) => (
      '<div class="stat-card">' +
      '<div style="font-size:11px;color:var(--text-muted)">' + title + '</div>' +
      '<div style="font-size:22px;font-weight:700;color:' + color + '">' + value + '</div>' +
      '</div>'
    )).join('');
  }

  function renderTasks(tasks) {
    const mount = el('tasksList');
    if (!mount) return;
    if (!tasks.length) {
      mount.innerHTML = '<p style="color: var(--text-muted); font-size: 12px;">Задачі не знайдені</p>';
      return;
    }

    mount.innerHTML = tasks.slice(0, 40).map((task) => (
      '<div class="task-item">' +
      '<div style="display:flex;justify-content:space-between;gap:8px;">' +
      '<strong style="font-size:12px">' + (task.building_address || 'Без адреси') + '</strong>' +
      '<span style="font-size:11px;color:' + statusColor(task.status) + '">' + statusLabel(task.status) + '</span>' +
      '</div>' +
      '<div style="font-size:11px;color:var(--text-secondary)">' + (task.description || 'Без опису') + '</div>' +
      '<div style="font-size:10px;color:var(--text-muted)">Бригада: ' + (task.brigade_name || '—') + '</div>' +
      '</div>'
    )).join('');
  }

  function renderBuildings() {
    const mount = el('buildingsList');
    if (!mount) return;
    if (!state.buildings.length) {
      mount.innerHTML = '<p style="color: var(--text-muted); font-size: 12px;">Будинки не знайдені</p>';
      return;
    }
    mount.innerHTML = state.buildings.slice(0, 20).map((building) => (
      '<div class="task-item">' +
      '<strong style="font-size:12px">' + (building.address || '—') + '</strong>' +
      '<div style="font-size:11px;color:var(--text-secondary)">' +
      (building.city || '—') + ' · під\'їздів: ' + (building.entrances_count || 0) +
      '</div>' +
      '</div>'
    )).join('');
  }

  function renderBrigades() {
    const mount = el('brigadesList');
    if (!mount) return;
    if (!state.brigades.length) {
      mount.innerHTML = '<p style="color: var(--text-muted); font-size: 12px;">Бригади не знайдені</p>';
      return;
    }
    mount.innerHTML = state.brigades.map((brigade) => (
      '<div class="task-item">' +
      '<strong style="font-size:12px">' + brigade.name + '</strong>' +
      '<div style="font-size:11px;color:var(--text-secondary)">' + (brigade.type || '—') + '</div>' +
      '</div>'
    )).join('');
  }

  function pushEvent(text) {
    const mount = el('eventFeed');
    if (!mount) return;
    const ts = new Date().toLocaleTimeString('uk-UA');
    const row = document.createElement('div');
    row.className = 'task-item';
    row.innerHTML = '<strong style="font-size:10px;color:var(--text-muted)">' + ts + '</strong>' +
      '<div style="font-size:11px">' + text + '</div>';
    mount.prepend(row);
    while (mount.children.length > 25) mount.removeChild(mount.lastChild);
  }

  async function renderAll() {
    const filtered = applyTaskFilters(state.tasks);
    renderStats(filtered);
    renderTasks(filtered);
    renderBuildings();
    renderBrigades();
  }

  async function refreshBoard(reason) {
    await loadAll();
    await renderAll();
    if (reason) pushEvent(reason);
  }

  async function createBrigade() {
    const name = (el('groupName')?.value || '').trim();
    const type = el('groupType')?.value || 'construction';
    if (!name) return;
    await FiberAuth.fetchJson('/api/brigades', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, type })
    });
    if (el('groupName')) el('groupName').value = '';
    await refreshBoard('Створено нову бригаду: ' + name);
  }

  function bindSocket() {
    if (!window.io) return;
    const token = FiberAuth.getStoredToken();
    if (!token) return;
    const socket = window.io({ auth: { token }, transports: ['websocket', 'polling'] });
    socket.on('connect', () => pushEvent('Realtime підключено'));
    socket.on('disconnect', () => pushEvent('Realtime відключено'));
    socket.on('progress.update', () => refreshBoard('Оновлено прогрес задач').catch(console.error));
    socket.on('subscriber_request.update', () => refreshBoard('Оновлено заявки').catch(console.error));
  }

  async function boot() {
    try {
      await FiberAuth.requireAuth({ roles: ['Dispatcher', 'ConnectionDispatcher'] });
      FiberAuth.bindUserBar();
    } catch (err) {
      if (err && err.message === 'forbidden-role') {
        window.location.href = FiberAuth.routeForRoles(FiberAuth.getStoredUser());
        return;
      }
      window.location.href = '/login?next=%2Fdispatcher';
      return;
    }

    el('refreshTasks')?.addEventListener('click', () => refreshBoard('Оновлено вручну').catch(console.error));
    el('filterSearch')?.addEventListener('input', () => renderAll().catch(console.error));
    el('filterStatus')?.addEventListener('change', () => renderAll().catch(console.error));
    el('createGroup')?.addEventListener('click', () => createBrigade().catch(console.error));

    await refreshBoard('Панель завантажено');
    bindSocket();
  }

  boot().catch(console.error);
})();
