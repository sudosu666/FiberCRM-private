(function () {
  'use strict';

  const S = {
    stock: [],
    requests: [],
    transactions: [],
    materialPlan: [],
    executionFacts: []
  };

  const el = (id) => document.getElementById(id);

  async function api(url, opts) {
    return FiberAuth.fetchJson(url, opts || {});
  }

  function dt(value) {
    if (!value) return '—';
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return String(value);
    return parsed.toLocaleString('uk-UA');
  }

  function renderStock() {
    const root = el('stockList');
    if (!root) return;
    if (!S.stock.length) {
      root.innerHTML = '<p class="placeholder">Склад порожній</p>';
      return;
    }

    root.innerHTML = S.stock.map((item) => {
      const shortage = Number(item.quantity) < Number(item.min_quantity || 0);
      return (
        '<div class="item">' +
        '<div style="display:flex;justify-content:space-between;gap:8px;">' +
        '<div class="item-title">' + item.name + '</div>' +
        '<span class="pill ' + (shortage ? 'warn' : 'ok') + '">' + (shortage ? 'shortage' : 'ok') + '</span>' +
        '</div>' +
        '<div class="item-sub">' + Number(item.quantity).toFixed(1) + ' ' + item.unit + ' · min ' + Number(item.min_quantity).toFixed(1) + '</div>' +
        '</div>'
      );
    }).join('');

    const selectA = el('adjustStockItem');
    const selectB = el('requestStockItem');
    const options = S.stock.map((item) => '<option value="' + item.id + '">' + item.name + ' (' + item.unit + ')</option>').join('');
    if (selectA) selectA.innerHTML = options;
    if (selectB) selectB.innerHTML = options;
  }

  function renderRequests() {
    const root = el('requestList');
    if (!root) return;
    if (!S.requests.length) {
      root.innerHTML = '<p class="placeholder">Запитів поки немає</p>';
      return;
    }
    root.innerHTML = S.requests.map((req) => {
      const items = (req.items || []).map((i) => {
        const planned = Number(i.planned_qty || 0);
        const fulfilled = Number(i.fulfilled_qty || 0);
        return i.stock_item_name + ': ' + fulfilled.toFixed(1) + '/' + planned.toFixed(1) + ' ' + (i.stock_item_unit || '');
      }).join(', ');
      const canFulfill = req.status === 'pending' || req.status === 'partial';
      return (
        '<div class="item">' +
        '<div style="display:flex;justify-content:space-between;gap:8px;">' +
        '<div class="item-title">Запит #' + String(req.id).slice(0, 8) + '</div>' +
        '<span class="pill ' + (req.status === 'fulfilled' ? 'ok' : 'warn') + '">' + req.status + '</span>' +
        '</div>' +
        '<div class="item-sub">' + (req.building_address || 'без будинку') + '</div>' +
        '<div class="item-sub">Хто запросив: ' + (req.requested_by_name || '—') + ' · ' + dt(req.created_at) + '</div>' +
        '<div class="item-sub">Підтвердив склад: ' + (req.fulfilled_by_name || '—') + ' · ' + dt(req.fulfilled_at) + '</div>' +
        '<div class="item-sub">' + items + '</div>' +
        (canFulfill ? '<button class="fulfill-btn" data-fulfill="' + req.id + '">Підтвердити видачу</button>' : '') +
        '</div>'
      );
    }).join('');
  }

  function renderMaterialPlan() {
    const root = el('materialPlanList');
    if (!root) return;
    if (!S.materialPlan.length) {
      root.innerHTML = '<p class="placeholder">Немає активних задач для планування</p>';
      return;
    }
    root.innerHTML = S.materialPlan.map((entry) => {
      const items = (entry.items || []).slice(0, 8).map((i) => i.stock_item_name + ': ' + Number(i.suggested_qty || 0).toFixed(1) + ' ' + i.unit).join(', ');
      const requestState = entry.latest_request_status || 'no_request';
      return (
        '<div class="item">' +
        '<div style="display:flex;justify-content:space-between;gap:8px;">' +
        '<div class="item-title">Task ' + String(entry.task_id).slice(0, 8) + '</div>' +
        '<span class="pill ' + (requestState === 'fulfilled' ? 'ok' : 'warn') + '">' + requestState + '</span>' +
        '</div>' +
        '<div class="item-sub">' + (entry.building_address || 'без адреси') + '</div>' +
        '<div class="item-sub">Статус задачі: ' + (entry.task_status || '—') + '</div>' +
        '<div class="item-sub">План: ' + (items || 'немає рекомендацій') + '</div>' +
        '</div>'
      );
    }).join('');
  }

  function renderTransactions() {
    const root = el('transactionsList');
    if (!root) return;
    if (!S.transactions.length) {
      root.innerHTML = '<p class="placeholder">Рухів поки немає</p>';
      return;
    }
    root.innerHTML = S.transactions.slice(0, 30).map((trx) => {
      const sign = Number(trx.delta) >= 0 ? '+' : '';
      return (
        '<div class="item">' +
        '<div class="item-title">' + trx.stock_item_name + '</div>' +
        '<div class="item-sub">' + sign + Number(trx.delta).toFixed(1) + ' · ' + (trx.reason || '—') + '</div>' +
        '</div>'
      );
    }).join('');
  }

  function renderExecutionFacts() {
    const root = el('executionFactsList');
    if (!root) return;
    if (!S.executionFacts.length) {
      root.innerHTML = '<p class="placeholder">Немає фактів або блокерів</p>';
      return;
    }
    root.innerHTML = S.executionFacts.map((entry) => {
      const facts = (entry.facts || []).map((fact) => {
        return fact.material_title + ': взято ' + Number(fact.taken_qty || 0).toFixed(1) +
          ', використано ' + Number(fact.used_qty || 0).toFixed(1) +
          ', списано ' + Number(fact.wasted_qty || 0).toFixed(1) +
          ', дельта ' + Number(fact.delta_qty || 0).toFixed(1);
      }).join('; ');
      return (
        '<div class="item">' +
        '<div style="display:flex;justify-content:space-between;gap:8px;">' +
        '<div class="item-title">Task ' + String(entry.task_id).slice(0, 8) + '</div>' +
        '<span class="pill ' + (entry.has_material_block ? 'warn' : 'ok') + '">' + (entry.has_material_block ? 'blocked' : 'ok') + '</span>' +
        '</div>' +
        '<div class="item-sub">' + (entry.building_address || 'без адреси') + ' · статус: ' + entry.task_status + '</div>' +
        '<div class="item-sub">Завершено: ' + dt(entry.completed_at) + '</div>' +
        '<div class="item-sub">' + (entry.material_block_reason || 'Блокерів немає') + '</div>' +
        '<div class="item-sub">' + (facts || 'Факт витрат ще не зафіксовано') + '</div>' +
        '</div>'
      );
    }).join('');
  }

  async function loadAll() {
    const [stock, requests, transactions, materialPlan, executionFacts] = await Promise.all([
      api('/api/stock'),
      api('/api/warehouse/requests'),
      api('/api/stock/transactions'),
      api('/api/warehouse/tasks/material-plan'),
      api('/api/warehouse/execution-facts')
    ]);
    S.stock = stock || [];
    S.requests = requests || [];
    S.transactions = transactions || [];
    S.materialPlan = materialPlan || [];
    S.executionFacts = executionFacts || [];
    renderStock();
    renderRequests();
    renderTransactions();
    renderMaterialPlan();
    renderExecutionFacts();
  }

  async function adjustStock() {
    const stock_item_id = el('adjustStockItem')?.value;
    const delta = parseFloat(el('adjustDelta')?.value || '0');
    const reason = (el('adjustReason')?.value || '').trim();
    if (!stock_item_id || !delta || !reason) return;

    await api('/api/stock/adjust', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stock_item_id, delta, reason })
    });
    if (el('adjustDelta')) el('adjustDelta').value = '';
    if (el('adjustReason')) el('adjustReason').value = '';
    await loadAll();
  }

  async function createRequest() {
    const stock_item_id = el('requestStockItem')?.value;
    const planned_qty = parseFloat(el('requestQty')?.value || '0');
    const notes = (el('requestNote')?.value || '').trim() || undefined;
    if (!stock_item_id || !planned_qty) return;

    await api('/api/warehouse/requests', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        notes,
        items: [{ stock_item_id, planned_qty }]
      })
    });
    if (el('requestQty')) el('requestQty').value = '';
    if (el('requestNote')) el('requestNote').value = '';
    await loadAll();
  }

  async function fulfillRequest(requestId) {
    const request = (S.requests || []).find((item) => String(item.id) === String(requestId));
    if (!request) return;
    const items = (request.items || []).map((item) => {
      const planned = Number(item.planned_qty || 0);
      const fulfilled = Number(item.fulfilled_qty || 0);
      const remaining = Math.max(0, planned - fulfilled);
      return { item_id: item.id, fulfilled_qty: remaining };
    }).filter((item) => item.fulfilled_qty > 0);
    if (!items.length) return;
    await api('/api/warehouse/requests/' + requestId + '/fulfill', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items })
    });
    await loadAll();
  }

  async function boot() {
    try {
      await FiberAuth.requireAuth({ roles: ['Warehouse'] });
      FiberAuth.bindUserBar();
    } catch (err) {
      if (err && err.message === 'forbidden-role') {
        window.location.href = FiberAuth.routeForRoles(FiberAuth.getStoredUser());
        return;
      }
      window.location.href = '/login?next=%2Fwarehouse';
      return;
    }

    el('refreshStock')?.addEventListener('click', () => loadAll().catch(console.error));
    el('refreshRequests')?.addEventListener('click', () => loadAll().catch(console.error));
    el('refreshTransactions')?.addEventListener('click', () => loadAll().catch(console.error));
    el('refreshPlan')?.addEventListener('click', () => loadAll().catch(console.error));
    el('refreshFacts')?.addEventListener('click', () => loadAll().catch(console.error));
    el('adjustStock')?.addEventListener('click', () => adjustStock().catch(console.error));
    el('createRequest')?.addEventListener('click', () => createRequest().catch(console.error));
    el('requestList')?.addEventListener('click', (event) => {
      const target = event.target;
      if (!target || !target.getAttribute) return;
      const requestId = target.getAttribute('data-fulfill');
      if (!requestId) return;
      fulfillRequest(requestId).catch(console.error);
    });

    await loadAll().catch(console.error);
  }

  boot().catch(console.error);
})();
