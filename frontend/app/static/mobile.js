(function () {
  'use strict';

  const S = {
    tasks: [],
    activeTask: null,
    steps: [],
    socket: null,
    socketBrigadeId: null,
    workRates: [],
    workEntries: [],
    stock: [],
    materialSuggestion: null,
    materialDraft: [],
    materialGateSatisfied: true
  };

  const el = (id) => document.getElementById(id);

  async function api(url, opts) {
    return FiberAuth.fetchJson(url, opts || {});
  }

  function toast(text, isError) {
    const node = el('taskActionHint');
    if (!node) return;
    node.textContent = text;
    node.style.color = isError ? '#f87171' : '';
  }

  function normalizeStatus(status) {
    return String(status || '').toLowerCase();
  }

  function statusLabel(status) {
    const map = {
      pending: 'очікування',
      assigned: 'призначено',
      in_progress: 'в роботі',
      completed: 'виконано',
      canceled: 'скасовано',
      on_hold: 'пауза'
    };
    return map[status] || status || '—';
  }

  function setDisabled(id, disabled) {
    const node = el(id);
    if (!node) return;
    node.disabled = Boolean(disabled);
  }

  function canStart(task) {
    const status = normalizeStatus(task && task.status);
    return Boolean(task) && ['pending', 'assigned', 'on_hold'].includes(status);
  }

  function needsWarehouseApprove(task) {
    const type = String(task && task.type || '').toLowerCase();
    return type === 'construction' || type === 'welding';
  }

  function canFinish(task) {
    const status = normalizeStatus(task && task.status);
    return Boolean(task) && ['in_progress', 'assigned'].includes(status);
  }

  function canPause(task) {
    const status = normalizeStatus(task && task.status);
    return Boolean(task) && ['assigned', 'in_progress'].includes(status);
  }

  function updateActionState() {
    const task = S.activeTask;
    const hasTask = Boolean(task);
    const hasPendingStep = (S.steps || []).some((step) => !step.is_done);
    const chatOnline = Boolean(S.socket && S.socket.connected);
    const materialBlocked = hasTask && needsWarehouseApprove(task) && !S.materialGateSatisfied;

    setDisabled('startTask', !canStart(task) || materialBlocked);
    setDisabled('finishTask', !canFinish(task));
    setDisabled('holdTask', !canPause(task));
    setDisabled('postponeTask', !canPause(task));
    setDisabled('holdCritical', !canPause(task));
    setDisabled('holdReason', !canPause(task));
    setDisabled('postponeReason', !canPause(task));
    setDisabled('advanceStep', !(hasTask && hasPendingStep && canPause(task)));
    setDisabled('chatInput', !chatOnline);
    setDisabled('chatSend', !chatOnline);
    setDisabled('addWorkEntry', !(hasTask && S.workRates.length));

    if (!hasTask) {
      toast('Оберіть задачу для дій', false);
      return;
    }
    const status = normalizeStatus(task.status);
    if (status === 'completed') {
      toast('Задача завершена: доступний лише перегляд', false);
      return;
    }
    if (materialBlocked) {
      toast('Спочатку: запит матеріалів -> підтвердження складу', true);
      return;
    }
    toast('Дії активні для поточної задачі', false);
  }

  function renderMaterialStockOptions() {
    const select = el('materialCustomStock');
    if (!select) return;
    if (!S.stock.length) {
      select.innerHTML = '<option value="">Немає складу</option>';
      return;
    }
    select.innerHTML = S.stock.map((item) => (
      '<option value="' + item.id + '">' + item.name + ' (' + item.unit + ')</option>'
    )).join('');
  }

  function renderMaterialDraft() {
    const root = el('materialsList');
    const status = el('materialsStatus');
    if (!root || !status) return;
    if (!S.activeTask) {
      status.textContent = 'Оберіть задачу для формування запиту на склад.';
      root.innerHTML = '<div class="placeholder">Немає активної задачі</div>';
      return;
    }
    if (!needsWarehouseApprove(S.activeTask)) {
      S.materialGateSatisfied = true;
      status.textContent = 'Для цієї задачі підтвердження складу не обовʼязкове.';
      root.innerHTML = '<div class="placeholder">Матеріали не потрібні для цього типу робіт</div>';
      return;
    }
    const latest = S.materialSuggestion && S.materialSuggestion.latest_request_status
      ? S.materialSuggestion.latest_request_status
      : 'no_request';
    if (latest === 'fulfilled') {
      status.textContent = 'Склад підтвердив видачу. Можна починати роботу.';
    } else if (latest === 'partial') {
      status.textContent = 'Склад видав частково. Старт задачі заблоковано.';
    } else if (latest === 'pending') {
      status.textContent = 'Запит на складі в очікуванні підтвердження.';
    } else {
      status.textContent = 'Сформуйте заявку та дочекайтесь підтвердження складу.';
    }
    if (!S.materialDraft.length) {
      root.innerHTML = '<div class="placeholder">Немає позицій. Додайте вручну.</div>';
      return;
    }
    root.innerHTML = S.materialDraft.map((item, idx) => (
      '<div class="task-card">' +
      '<div style="font-weight:600">' + item.stock_item_name + '</div>' +
      '<div class="secondary">ID: ' + String(item.stock_item_id).slice(0, 8) + '</div>' +
      '<div style="display:flex;gap:8px;margin-top:8px;">' +
      '<input data-material-qty="' + idx + '" type="number" min="0.1" step="0.1" value="' + Number(item.planned_qty).toFixed(1) + '" style="flex:1">' +
      '<span class="secondary" style="display:flex;align-items:center;">' + item.unit + '</span>' +
      '<button class="ghost" data-material-remove="' + idx + '" type="button">Видалити</button>' +
      '</div>' +
      '</div>'
    )).join('');
  }

  async function loadMaterialStage() {
    if (!S.activeTask) return;
    if (!needsWarehouseApprove(S.activeTask)) {
      S.materialSuggestion = null;
      S.materialDraft = [];
      S.materialGateSatisfied = true;
      renderMaterialDraft();
      updateActionState();
      return;
    }
    try {
      const [stock, suggestion] = await Promise.all([
        api('/api/stock'),
        api('/api/warehouse/tasks/' + S.activeTask.id + '/suggestions')
      ]);
      S.stock = stock || [];
      S.materialSuggestion = suggestion || null;
      S.materialGateSatisfied = Boolean(suggestion && suggestion.latest_request_status === 'fulfilled');
      const nextDraft = [];
      (suggestion && suggestion.items ? suggestion.items : []).forEach((item) => {
        if (!item.stock_item_id) return;
        nextDraft.push({
          stock_item_id: item.stock_item_id,
          stock_item_name: item.stock_item_name,
          unit: item.unit,
          planned_qty: Number(item.suggested_qty || 0)
        });
      });
      S.materialDraft = nextDraft;
      renderMaterialStockOptions();
      renderMaterialDraft();
      updateActionState();
    } catch (err) {
      toast('Не вдалося підготувати матеріали: ' + (err && err.message ? err.message : err), true);
    }
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
        loadMaterialStage().catch(console.error);
        ensureSocketForActiveTask();
      });
    });

    if (!S.activeTask) S.activeTask = S.tasks[0];
    renderStatusMeta();
    updateActionState();
  }

  function renderStatusMeta() {
    const node = el('taskStatusMeta');
    if (!node) return;
    if (!S.activeTask) {
      node.textContent = 'Статус: немає активної задачі';
      return;
    }
    node.textContent = 'Статус: ' + statusLabel(S.activeTask.status) + ' · task ' + String(S.activeTask.id).slice(0, 8);
  }

  function renderSteps() {
    const root = el('stepTimeline');
    if (!root) return;
    if (!S.steps.length) {
      root.innerHTML = '<div class="placeholder">Кроки не знайдено</div>';
      el('stepBadge').textContent = 'Кроків: 0';
      updateActionState();
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
    updateActionState();
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

  function renderWorkRates() {
    const select = el('workRateCode');
    if (!select) return;
    if (!S.workRates.length) {
      select.innerHTML = '<option value="">Немає розцінок</option>';
      setDisabled('addWorkEntry', true);
      return;
    }
    const current = select.value;
    select.innerHTML = S.workRates.map((rate) => (
      '<option value="' + rate.code + '">' + rate.title + ' · ' + rate.price_uah + ' грн/' + rate.unit + '</option>'
    )).join('');
    if (current) select.value = current;
    setDisabled('addWorkEntry', false);
    el('workRateStatus').textContent = 'rate: ' + S.workRates.length;
  }

  function renderWorkEntries() {
    const root = el('workEntriesList');
    if (!root) return;
    if (!S.workEntries.length) {
      root.innerHTML = '<div class="placeholder">Записів ще немає</div>';
      return;
    }
    root.innerHTML = S.workEntries.slice().reverse().map((entry) => (
      '<div class="task-item">' +
      '<strong>' + entry.title + '</strong>' +
      '<div class="secondary">' + entry.quantity + ' ' + entry.unit + ' × ' + entry.unit_price_uah + ' грн</div>' +
      '<div class="secondary">Сума: ' + entry.total_price_uah + ' грн</div>' +
      '<div class="secondary">' + (entry.notes || '—') + '</div>' +
      '</div>'
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
    try {
      S.tasks = await api('/api/tasks');
      renderTasks();
      updateActionState();
    } catch (err) {
      toast('Не вдалося завантажити задачі: ' + (err && err.message ? err.message : err), true);
      throw err;
    }
  }

  async function loadWorkRates() {
    try {
      S.workRates = await api('/api/work-rates?active_only=true');
    } catch (_err) {
      S.workRates = [];
    }
    renderWorkRates();
  }

  async function loadSteps() {
    if (!S.activeTask) return;
    try {
      S.steps = await api('/api/tasks/' + S.activeTask.id + '/steps');
      renderSteps();
    } catch (err) {
      toast('Не вдалося завантажити кроки: ' + (err && err.message ? err.message : err), true);
      throw err;
    }
  }

  async function patchTask(path, payload) {
    if (!S.activeTask) return;
    try {
      await api('/api/tasks/' + S.activeTask.id + path, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload || {})
      });
      await loadTasks();
      const fresh = S.tasks.find((task) => String(task.id) === String(S.activeTask.id));
      if (fresh) S.activeTask = fresh;
      await loadSteps();
      await loadMaterialStage();
    } catch (err) {
      toast('Операцію не виконано: ' + (err && err.message ? err.message : err), true);
      throw err;
    }
  }

  function numberInputValue(id) {
    const raw = (el(id)?.value || '').trim();
    if (!raw) return 0;
    const value = Number(raw);
    if (!Number.isFinite(value) || value < 0) return 0;
    return value;
  }

  async function completeTaskWithActuals() {
    if (!S.activeTask) {
      toast('Немає активної задачі', true);
      return;
    }
    const payload = {
      cable_indoor_m: numberInputValue('actualCableIndoor'),
      cable_outdoor_m: numberInputValue('actualCableOutdoor'),
      cable_air_m: numberInputValue('actualCableAir'),
      cable_wasted_m: numberInputValue('actualCableWaste'),
      boxes_qty: numberInputValue('actualBoxes'),
      tubes_qty: numberInputValue('actualTubes'),
      fops_qty: numberInputValue('actualFops'),
      notes: (el('actualNote')?.value || '').trim() || null
    };
    try {
      const result = await api('/api/tasks/' + S.activeTask.id + '/complete-with-actuals', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const summary = el('completionSummary');
      if (summary) {
        const facts = Array.isArray(result.facts) ? result.facts : [];
        summary.innerHTML =
          '<strong>Задачу завершено.</strong> Бригада: ' + (result.brigade_total_amount_uah || 0) + ' грн · На одного: ' + (result.per_member_amount_uah || 0) + ' грн' +
          '<br>' + facts.map((fact) => (
            fact.material_title + ': взято ' + fact.taken_qty + ', використано ' + fact.used_qty + ', списано ' + fact.wasted_qty + ', дельта ' + fact.delta_qty
          )).join('<br>');
      }
      await loadTasks();
      const fresh = S.tasks.find((task) => String(task.id) === String(S.activeTask.id));
      if (fresh) S.activeTask = fresh;
      await loadSteps();
      toast('Завершення з фактом виконання збережено', false);
    } catch (err) {
      toast('Помилка завершення: ' + (err && err.message ? err.message : err), true);
    }
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
      setDisabled('refreshTasks', true);
      loadTasks().then(loadSteps).catch(console.error);
      setTimeout(() => setDisabled('refreshTasks', false), 600);
    });
    el('startTask')?.addEventListener('click', () => patchTask('/start').catch(console.error));
    el('finishTask')?.addEventListener('click', () => completeTaskWithActuals().catch(console.error));
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
      try {
        await api('/api/tasks/' + S.activeTask.id + '/steps/' + pending.id + '/complete', { method: 'PATCH' });
        await loadTasks();
        await loadSteps();
      } catch (err) {
        toast('Не вдалося оновити крок: ' + (err && err.message ? err.message : err), true);
      }
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
        const user = FiberAuth.getStoredUser();
        S.socket.emit('chat.message', {
          message: text,
          user: user && user.name ? user.name : 'Бригада',
          brigade_id: S.activeTask ? S.activeTask.brigade_id : null,
          task_id: S.activeTask ? S.activeTask.id : null,
          timestamp: new Date().toISOString()
        });
      }
    });

    el('addWorkEntry')?.addEventListener('click', async () => {
      if (!S.activeTask) {
        toast('Немає активної задачі для фіксації робіт', true);
        return;
      }
      const workCode = el('workRateCode')?.value || '';
      const quantity = Number(el('workQuantity')?.value || '0');
      const notes = (el('workNote')?.value || '').trim() || null;
      if (!workCode || !Number.isFinite(quantity) || quantity <= 0) {
        toast('Оберіть роботу і вкажіть коректну кількість', true);
        return;
      }
      try {
        const entry = await api('/api/tasks/' + S.activeTask.id + '/work-entries', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ work_code: workCode, quantity, notes })
        });
        S.workEntries.push(entry);
        renderWorkEntries();
        toast('Роботу зафіксовано для розрахунку', false);
        if (el('workNote')) el('workNote').value = '';
      } catch (err) {
        toast('Помилка фіксації роботи: ' + (err && err.message ? err.message : err), true);
      }
    });

    el('refreshMaterials')?.addEventListener('click', () => loadMaterialStage().catch(console.error));
    el('addMaterialItem')?.addEventListener('click', () => {
      const stockId = el('materialCustomStock')?.value;
      const qty = Number(el('materialCustomQty')?.value || '0');
      if (!stockId || !Number.isFinite(qty) || qty <= 0) {
        toast('Вкажіть позицію і кількість матеріалу', true);
        return;
      }
      const stockItem = (S.stock || []).find((item) => String(item.id) === String(stockId));
      if (!stockItem) return;
      const existing = (S.materialDraft || []).find((item) => String(item.stock_item_id) === String(stockId));
      if (existing) {
        existing.planned_qty = Number(existing.planned_qty || 0) + qty;
      } else {
        S.materialDraft.push({
          stock_item_id: stockItem.id,
          stock_item_name: stockItem.name,
          unit: stockItem.unit,
          planned_qty: qty
        });
      }
      if (el('materialCustomQty')) el('materialCustomQty').value = '';
      renderMaterialDraft();
    });
    el('materialsList')?.addEventListener('input', (event) => {
      const target = event.target;
      if (!target || !target.getAttribute) return;
      const idx = target.getAttribute('data-material-qty');
      if (idx === null) return;
      const num = Number(target.value || '0');
      const row = S.materialDraft[Number(idx)];
      if (!row) return;
      row.planned_qty = Number.isFinite(num) && num > 0 ? num : 0;
    });
    el('materialsList')?.addEventListener('click', (event) => {
      const target = event.target;
      if (!target || !target.getAttribute) return;
      const idx = target.getAttribute('data-material-remove');
      if (idx === null) return;
      S.materialDraft.splice(Number(idx), 1);
      renderMaterialDraft();
    });
    el('submitMaterialsRequest')?.addEventListener('click', async () => {
      if (!S.activeTask) {
        toast('Немає активної задачі', true);
        return;
      }
      if (!needsWarehouseApprove(S.activeTask)) {
        toast('Для цієї задачі етап матеріалів не потрібен', true);
        return;
      }
      const items = (S.materialDraft || [])
        .filter((item) => Number(item.planned_qty || 0) > 0 && item.stock_item_id)
        .map((item) => ({
          stock_item_id: item.stock_item_id,
          planned_qty: Number(item.planned_qty || 0)
        }));
      if (!items.length) {
        toast('Додайте хоча б одну позицію матеріалів', true);
        return;
      }
      try {
        await api('/api/warehouse/tasks/' + S.activeTask.id + '/requests/propose', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            notes: 'Crew request from field panel',
            items: items
          })
        });
        toast('Запит на склад відправлено', false);
        await loadMaterialStage();
      } catch (err) {
        toast('Не вдалося створити запит: ' + (err && err.message ? err.message : err), true);
      }
    });
  }

  function ensureSocketForActiveTask() {
    if (!window.io) return;
    const token = FiberAuth.getStoredToken();
    if (!token) return;
    const brigadeId = S.activeTask && S.activeTask.brigade_id ? String(S.activeTask.brigade_id) : null;
    if (!brigadeId) {
      el('chatStatus').textContent = 'offline';
      setDisabled('chatInput', true);
      setDisabled('chatSend', true);
      return;
    }
    if (S.socket && S.socket.connected && S.socketBrigadeId === brigadeId) return;
    if (S.socket) {
      S.socket.disconnect();
      S.socket = null;
    }
    S.socketBrigadeId = brigadeId;
    const socket = window.io({
      auth: { token, brigade_id: brigadeId },
      transports: ['websocket', 'polling']
    });
    S.socket = socket;
    socket.on('connect', () => {
      el('chatStatus').textContent = 'online';
      el('signalStrength').textContent = '🛰️ Online';
      toast('Realtime підключено', false);
      updateActionState();
    });
    socket.on('disconnect', () => {
      el('chatStatus').textContent = 'offline';
      el('signalStrength').textContent = '🛰️ Offline';
      updateActionState();
    });
    socket.on('chat.message', (payload) => {
      appendChat(payload?.user || payload?.author_name || 'Диспетчер', payload?.message || payload?.body || '');
    });
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
    el('syncStatus').textContent = 'Синхронізація: online';
    await loadTasks();
    await loadSteps();
    await loadMaterialStage();
    await loadWorkRates();
    renderWorkEntries();
    ensureSocketForActiveTask();
    updateActionState();
  }

  boot().catch(console.error);
})();
