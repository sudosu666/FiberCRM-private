(function () {
  'use strict';

  const state = {
    tasks: [],
    buildings: [],
    brigades: [],
    workers: []
  };

  function syncEntityBridge() {
    if (!window.DispatcherEntityBridge || typeof window.DispatcherEntityBridge.setData !== 'function') return;
    window.DispatcherEntityBridge.setData({
      tasks: state.tasks,
      buildings: state.buildings,
      brigades: state.brigades,
      workers: state.workers
    });
  }

  function el(id) {
    return document.getElementById(id);
  }

  function safe(text) {
    return String(text || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  async function loadAll() {
    const [tasks, buildings, brigades, workers] = await Promise.all([
      FiberAuth.fetchJson('/api/tasks'),
      FiberAuth.fetchJson('/api/buildings'),
      FiberAuth.fetchJson('/api/brigades'),
      FiberAuth.fetchJson('/api/field/workers')
    ]);
    state.tasks = Array.isArray(tasks) ? tasks : [];
    state.buildings = Array.isArray(buildings) ? buildings : [];
    state.brigades = Array.isArray(brigades) ? brigades : [];
    state.workers = Array.isArray(workers) ? workers : [];
    syncEntityBridge();
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

    const brigadeOptions = '<option value="">— Без бригади —</option>' + state.brigades.map((brigade) => (
      '<option value="' + safe(brigade.id) + '">' + safe(brigade.name) + '</option>'
    )).join('');

    mount.innerHTML = tasks.slice(0, 40).map((task) => (
      '<div class="task-item">' +
      '<div style="display:flex;justify-content:space-between;gap:8px;">' +
      '<strong class="entity-link" data-entity="task" data-id="' + safe(task.id) + '" style="font-size:12px">' + safe(task.building_address || 'Без адреси') + '</strong>' +
      '<span style="font-size:11px;color:' + statusColor(task.status) + '">' + statusLabel(task.status) + '</span>' +
      '</div>' +
      '<div style="font-size:11px;color:var(--text-secondary)">' + safe(task.description || 'Без опису') + '</div>' +
      '<div style="font-size:10px;color:var(--text-muted)">Бригада: ' + safe(task.brigade_name || '—') + '</div>' +
      '<div class="compact-row">' +
      '<select data-task-brigade="' + safe(task.id) + '">' + brigadeOptions + '</select>' +
      '<button class="btn btn-ghost btn-sm" data-action="assign-task" data-id="' + safe(task.id) + '">Призначити</button>' +
      '<button class="btn btn-ghost btn-sm" data-action="unassign-task" data-id="' + safe(task.id) + '"' + (task.brigade_id ? '' : ' disabled') + '>Відкликати</button>' +
      '</div>' +
      '</div>'
    )).join('');

    tasks.slice(0, 40).forEach((task) => {
      const select = mount.querySelector('[data-task-brigade="' + String(task.id) + '"]');
      if (select) select.value = task.brigade_id ? String(task.brigade_id) : '';
    });

    mount.querySelectorAll('[data-action="assign-task"]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const taskId = btn.getAttribute('data-id');
        const select = mount.querySelector('[data-task-brigade="' + String(taskId) + '"]');
        const brigadeId = select ? select.value : '';
        if (!brigadeId) {
          pushEvent('Оберіть бригаду для призначення');
          return;
        }
        await assignTask(taskId, brigadeId);
      });
    });
    mount.querySelectorAll('[data-action="unassign-task"]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const taskId = btn.getAttribute('data-id');
        await unassignTask(taskId);
      });
    });
    mount.querySelectorAll('[data-entity="task"]').forEach((node) => {
      node.addEventListener('click', () => showEntityDetails('task', node.getAttribute('data-id')));
    });
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
      '<strong class="entity-link" data-entity="building" data-id="' + safe(building.id) + '" style="font-size:12px">' + safe(building.address || '—') + '</strong>' +
      '<div style="font-size:11px;color:var(--text-secondary)">' +
      safe(building.city || '—') + ' · під\'їздів: ' + (building.entrances_count || 0) +
      '</div>' +
      '</div>'
    )).join('');
    mount.querySelectorAll('[data-entity="building"]').forEach((node) => {
      node.addEventListener('click', () => showEntityDetails('building', node.getAttribute('data-id')));
    });
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
      '<strong class="entity-link" data-entity="brigade" data-id="' + safe(brigade.id) + '" style="font-size:12px">' + safe(brigade.name) + '</strong>' +
      '<div style="font-size:11px;color:var(--text-secondary)">' + safe(brigade.type || '—') + ' · ' + safe(brigade.status_label || '—') + '</div>' +
      '<div class="compact-row">' +
      '<button class="btn btn-ghost btn-sm" data-action="toggle-brigade" data-id="' + safe(brigade.id) + '" data-active="' + (brigade.is_active ? '1' : '0') + '">' + (brigade.is_active ? 'Відкликати' : 'Активувати') + '</button>' +
      '<button class="btn btn-ghost btn-sm" data-action="delete-brigade" data-id="' + safe(brigade.id) + '">Видалити</button>' +
      '</div>' +
      '</div>'
    )).join('');

    mount.querySelectorAll('[data-entity="brigade"]').forEach((node) => {
      node.addEventListener('click', () => showEntityDetails('brigade', node.getAttribute('data-id')));
    });
    mount.querySelectorAll('[data-action="toggle-brigade"]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const brigadeId = btn.getAttribute('data-id');
        const active = btn.getAttribute('data-active') === '1';
        await setBrigadeActive(brigadeId, !active);
      });
    });
    mount.querySelectorAll('[data-action="delete-brigade"]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const brigadeId = btn.getAttribute('data-id');
        await deleteBrigade(brigadeId);
      });
    });
  }

  function renderWorkers() {
    const mount = el('workersList');
    if (!mount) return;
    if (!state.workers.length) {
      mount.innerHTML = '<p style="color: var(--text-muted); font-size: 12px;">Співробітники не знайдені</p>';
      return;
    }
    mount.innerHTML = state.workers.map((worker) => (
      '<div class="task-item">' +
      '<strong class="entity-link" data-entity="worker" data-id="' + safe(worker.id) + '" style="font-size:12px">' + safe(worker.name) + '</strong>' +
      '<div style="font-size:11px;color:var(--text-secondary)">' + safe(worker.phone || '—') + ' · ' + safe(worker.role || '—') + '</div>' +
      '<div style="font-size:10px;color:var(--text-muted)">Бригада: ' + safe(worker.brigade_name || '—') + '</div>' +
      '</div>'
    )).join('');
    mount.querySelectorAll('[data-entity="worker"]').forEach((node) => {
      node.addEventListener('click', () => showEntityDetails('worker', node.getAttribute('data-id')));
    });
  }

  function showEntityDetails(entityType, entityId) {
    if (window.DispatcherEntityBridge && typeof window.DispatcherEntityBridge.selectEntity === 'function') {
      window.DispatcherEntityBridge.selectEntity(entityType, entityId);
      return;
    }
    const mount = el('entityDetails');
    if (!mount) return;
    if (!entityId) {
      mount.textContent = 'Сутність не знайдена';
      return;
    }
    if (entityType === 'task') {
      const task = state.tasks.find((item) => String(item.id) === String(entityId));
      if (!task) {
        mount.textContent = 'Задача не знайдена';
        return;
      }
      mount.innerHTML =
        '<div><strong>Задача</strong></div>' +
        '<div>ID: ' + safe(task.id) + '</div>' +
        '<div>Адреса: ' + safe(task.building_address || '—') + '</div>' +
        '<div>Статус: ' + safe(statusLabel(task.status)) + '</div>' +
        '<div>Бригада: ' + safe(task.brigade_name || '—') + '</div>' +
        '<div>Пріоритет: ' + safe(task.priority) + '</div>' +
        '<div>Опис: ' + safe(task.description || '—') + '</div>';
      return;
    }
    if (entityType === 'building') {
      const building = state.buildings.find((item) => String(item.id) === String(entityId));
      if (!building) {
        mount.textContent = 'Будинок не знайдено';
        return;
      }
      mount.innerHTML =
        '<div><strong>Будинок</strong></div>' +
        '<div>ID: ' + safe(building.id) + '</div>' +
        '<div>Адреса: ' + safe(building.address || '—') + '</div>' +
        '<div>Місто: ' + safe(building.city || '—') + '</div>' +
        '<div>Під\'їзди: ' + safe(building.entrances_count || 0) + '</div>' +
        '<div>Поверхи: ' + safe(building.floors_count || 0) + '</div>' +
        '<div>Статус інфри: ' + safe(building.infrastructure_status || '—') + '</div>';
      return;
    }
    if (entityType === 'worker') {
      const worker = state.workers.find((item) => String(item.id) === String(entityId));
      if (!worker) {
        mount.textContent = 'Співробітника не знайдено';
        return;
      }
      mount.innerHTML =
        '<div><strong>Співробітник</strong></div>' +
        '<div>ID: ' + safe(worker.id) + '</div>' +
        '<div>ПІБ: ' + safe(worker.name || '—') + '</div>' +
        '<div>Телефон: ' + safe(worker.phone || '—') + '</div>' +
        '<div>Роль: ' + safe(worker.role || '—') + '</div>' +
        '<div>Бригада: ' + safe(worker.brigade_name || '—') + '</div>';
      return;
    }
    if (entityType === 'brigade') {
      const brigade = state.brigades.find((item) => String(item.id) === String(entityId));
      if (!brigade) {
        mount.textContent = 'Бригаду не знайдено';
        return;
      }
      mount.innerHTML =
        '<div><strong>Бригада</strong></div>' +
        '<div>ID: ' + safe(brigade.id) + '</div>' +
        '<div>Назва: ' + safe(brigade.name || '—') + '</div>' +
        '<div>Тип: ' + safe(brigade.type || '—') + '</div>' +
        '<div>Статус: ' + safe(brigade.status_label || '—') + '</div>' +
        '<div>Учасників: ' + safe(brigade.members || 0) + '</div>' +
        '<div>Активна: ' + (brigade.is_active ? 'так' : 'ні') + '</div>';
      return;
    }
    mount.textContent = 'Сутність не підтримується';
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
    renderWorkers();
    renderFinanceSelectors();
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

  async function assignTask(taskId, brigadeId) {
    try {
      await FiberAuth.fetchJson('/api/tasks/' + taskId + '/assign', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ brigade_id: brigadeId })
      });
      await refreshBoard('Задачу призначено бригаді');
    } catch (err) {
      pushEvent('Помилка призначення: ' + (err && err.message ? err.message : err));
    }
  }

  async function unassignTask(taskId) {
    try {
      await FiberAuth.fetchJson('/api/tasks/' + taskId + '/unassign', { method: 'PATCH' });
      await refreshBoard('Призначення задачі відкликано');
    } catch (err) {
      pushEvent('Помилка відкликання: ' + (err && err.message ? err.message : err));
    }
  }

  async function setBrigadeActive(brigadeId, isActive) {
    try {
      await FiberAuth.fetchJson('/api/brigades/' + brigadeId + '/active?is_active=' + String(Boolean(isActive)), {
        method: 'PATCH'
      });
      await refreshBoard(isActive ? 'Бригаду активовано' : 'Бригаду відкликано');
    } catch (err) {
      pushEvent('Помилка зміни статусу бригади: ' + (err && err.message ? err.message : err));
    }
  }

  async function deleteBrigade(brigadeId) {
    if (!window.confirm('Видалити бригаду? Призначені задачі будуть відкликані.')) return;
    try {
      await FiberAuth.fetchJson('/api/brigades/' + brigadeId, { method: 'DELETE' });
      await refreshBoard('Бригаду видалено');
    } catch (err) {
      pushEvent('Помилка видалення бригади: ' + (err && err.message ? err.message : err));
    }
  }

  function dateInputValue(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return y + '-' + m + '-' + d;
  }

  function renderFinanceSelectors() {
    const select = el('payoutBrigade');
    if (!select) return;
    const current = select.value;
    select.innerHTML = '<option value="">Оберіть бригаду</option>' + state.brigades.map((item) => (
      '<option value="' + safe(item.id) + '">' + safe(item.name) + '</option>'
    )).join('');
    if (current) select.value = current;
  }

  async function loadCalendarEvents() {
    const from = el('calendarFrom')?.value;
    const to = el('calendarTo')?.value;
    const mount = el('calendarList');
    if (!mount) return;
    try {
      const query = '?date_from=' + encodeURIComponent(from + 'T00:00:00') + '&date_to=' + encodeURIComponent(to + 'T23:59:59');
      const events = await FiberAuth.fetchJson('/api/calendar/events' + query);
      if (!Array.isArray(events) || events.length === 0) {
        mount.innerHTML = '<div style="color:var(--text-muted)">Подій за період немає</div>';
        return;
      }
      mount.innerHTML = events.slice(0, 120).map((event) => (
        '<div class="task-item">' +
        '<strong>' + safe(event.title) + '</strong>' +
        '<div style="color:var(--text-secondary)">' + safe(event.status) + ' · ' + safe(event.building_address || '—') + '</div>' +
        '<div style="color:var(--text-muted)">' + safe(event.starts_at) + '</div>' +
        '</div>'
      )).join('');
    } catch (err) {
      mount.innerHTML = '<div style="color:var(--danger)">Помилка календаря: ' + safe(err && err.message ? err.message : err) + '</div>';
    }
  }

  async function calcPayout() {
    const brigadeId = el('payoutBrigade')?.value || '';
    const from = el('calendarFrom')?.value;
    const to = el('calendarTo')?.value;
    const mount = el('payoutBox');
    if (!mount) return;
    if (!brigadeId) {
      mount.textContent = 'Оберіть бригаду';
      return;
    }
    try {
      const query = '?date_from=' + encodeURIComponent(from + 'T00:00:00') + '&date_to=' + encodeURIComponent(to + 'T23:59:59');
      const payout = await FiberAuth.fetchJson('/api/brigades/' + brigadeId + '/payout' + query);
      mount.innerHTML =
        '<div>Бригада: <strong>' + safe(payout.brigade_name || '—') + '</strong></div>' +
        '<div>Робіт: ' + safe(payout.entries_count) + '</div>' +
        '<div>Сума: <strong>' + safe(payout.total_amount_uah) + ' грн</strong></div>' +
        '<div>Учасників: ' + safe(payout.members_count) + '</div>' +
        '<div>На одного: <strong>' + safe(payout.per_member_amount_uah) + ' грн</strong></div>';
    } catch (err) {
      mount.innerHTML = '<div style="color:var(--danger)">Помилка виплат: ' + safe(err && err.message ? err.message : err) + '</div>';
    }
  }

  function buildAssignedTaskRows(tasks) {
    const assigned = tasks.filter((task) => Boolean(task.brigade_id));
    if (!assigned.length) {
      return '<tr><td colspan="6" style="padding:10px;color:#94a3b8">Немає призначених задач</td></tr>';
    }
    return assigned.map((task) => (
      '<tr>' +
      '<td style="padding:8px;border-bottom:1px solid #1f2937;">' + safe(task.building_address || '—') + '</td>' +
      '<td style="padding:8px;border-bottom:1px solid #1f2937;">' + safe(task.brigade_name || '—') + '</td>' +
      '<td style="padding:8px;border-bottom:1px solid #1f2937;color:' + safe(statusColor(task.status)) + ';">' + safe(statusLabel(task.status)) + '</td>' +
      '<td style="padding:8px;border-bottom:1px solid #1f2937;">' + safe(task.type || '—') + '</td>' +
      '<td style="padding:8px;border-bottom:1px solid #1f2937;">' + safe(task.hold_reason || '—') + '</td>' +
      '<td style="padding:8px;border-bottom:1px solid #1f2937;">' + safe(task.status_changed_at || '—') + '</td>' +
      '</tr>'
    )).join('');
  }

  function openAssignedWindow() {
    const popup = window.open('', 'fiberops_assigned_tasks', 'width=1080,height=720');
    if (!popup) {
      pushEvent('Не вдалося відкрити вікно статусів (popup blocked)');
      return;
    }
    popup.document.open();
    popup.document.write(
      '<!doctype html><html lang="uk"><head><meta charset="utf-8">' +
      '<meta name="viewport" content="width=device-width, initial-scale=1">' +
      '<title>Статус призначених задач</title>' +
      '<style>' +
      'body{font-family:Inter,Arial,sans-serif;background:#0b1220;color:#e2e8f0;margin:0;padding:16px;}' +
      'h1{font-size:18px;margin:0 0 6px 0;} .meta{font-size:12px;color:#94a3b8;margin-bottom:12px;}' +
      'table{width:100%;border-collapse:collapse;background:#111827;border:1px solid #1f2937;border-radius:10px;overflow:hidden;}' +
      'th{font-size:11px;color:#94a3b8;text-align:left;padding:10px;border-bottom:1px solid #1f2937;text-transform:uppercase;}' +
      'button{background:#2563eb;color:#fff;border:none;border-radius:8px;padding:8px 12px;cursor:pointer;}' +
      '.row{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;gap:8px;}' +
      '</style></head><body>' +
      '<div class="row"><div><h1>Статус призначених задач</h1><div class="meta" id="stamp">Оновлення...</div></div>' +
      '<button id="reloadBtn" type="button">Оновити</button></div>' +
      '<table><thead><tr><th>Адреса</th><th>Бригада</th><th>Статус</th><th>Тип</th><th>Причина/Коментар</th><th>Оновлено</th></tr></thead>' +
      '<tbody id="rows">' + buildAssignedTaskRows(state.tasks) + '</tbody></table>' +
      '<script>' +
      '(function(){' +
      'const TOKEN_KEY="fiberops_token";' +
      'const rows=document.getElementById("rows"); const stamp=document.getElementById("stamp"); const btn=document.getElementById("reloadBtn");' +
      'function safe(v){return String(v||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/\\x27/g,"&#39;");}' +
      'function lbl(s){const m={pending:"Очікування",assigned:"Призначено",in_progress:"В роботі",completed:"Виконано",canceled:"Скасовано",on_hold:"Пауза"};return m[s]||s||"—";}' +
      'function color(s){if(s==="completed")return"#22c55e";if(s==="in_progress")return"#3b82f6";if(s==="assigned")return"#f59e0b";if(s==="canceled")return"#ef4444";return"#cbd5e1";}' +
      'function render(list){const assigned=(list||[]).filter(t=>Boolean(t.brigade_id)); if(!assigned.length){rows.innerHTML="<tr><td colspan=\\"6\\" style=\\"padding:10px;color:#94a3b8\\">Немає призначених задач</td></tr>";return;}' +
      'rows.innerHTML=assigned.map(t=>"<tr><td style=\\"padding:8px;border-bottom:1px solid #1f2937;\\">"+safe(t.building_address||"—")+"</td><td style=\\"padding:8px;border-bottom:1px solid #1f2937;\\">"+safe(t.brigade_name||"—")+"</td><td style=\\"padding:8px;border-bottom:1px solid #1f2937;color:"+color(t.status)+";\\">"+safe(lbl(t.status))+"</td><td style=\\"padding:8px;border-bottom:1px solid #1f2937;\\">"+safe(t.type||"—")+"</td><td style=\\"padding:8px;border-bottom:1px solid #1f2937;\\">"+safe(t.hold_reason||"—")+"</td><td style=\\"padding:8px;border-bottom:1px solid #1f2937;\\">"+safe(t.status_changed_at||"—")+"</td></tr>").join("");}' +
      'async function load(){const token=window.localStorage.getItem(TOKEN_KEY); if(!token){rows.innerHTML="<tr><td colspan=\\"6\\" style=\\"padding:10px;color:#ef4444\\">Немає токена авторизації</td></tr>";return;}' +
      'try{const r=await fetch("/api/tasks",{headers:{Authorization:"Bearer "+token}}); if(!r.ok) throw new Error("HTTP "+r.status); const data=await r.json(); render(data); stamp.textContent="Оновлено: "+new Date().toLocaleString("uk-UA");}catch(e){rows.innerHTML="<tr><td colspan=\\"6\\" style=\\"padding:10px;color:#ef4444\\">Помилка завантаження: "+safe(e.message||e)+"</td></tr>";}}' +
      'btn.addEventListener("click",load); load(); setInterval(load,15000);' +
      '})();' +
      '<\/script>' +
      '</body></html>'
    );
    popup.document.close();
    popup.focus();
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
    el('openAssignedWindow')?.addEventListener('click', openAssignedWindow);
    el('groupName')?.addEventListener('input', () => {
      const btn = el('createGroup');
      if (!btn) return;
      btn.disabled = !(el('groupName')?.value || '').trim();
    });
    const createBtn = el('createGroup');
    if (createBtn) createBtn.disabled = true;
    const now = new Date();
    const from = new Date(now);
    from.setDate(now.getDate() - 14);
    if (el('calendarFrom')) el('calendarFrom').value = dateInputValue(from);
    if (el('calendarTo')) el('calendarTo').value = dateInputValue(now);
    el('loadCalendar')?.addEventListener('click', () => loadCalendarEvents().catch(console.error));
    el('calcPayout')?.addEventListener('click', () => calcPayout().catch(console.error));

    await refreshBoard('Панель завантажено');
    await loadCalendarEvents();
    bindSocket();
  }

  boot().catch(console.error);
})();
