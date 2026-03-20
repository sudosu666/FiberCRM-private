(function () {
  'use strict';

  const S = {
    stock: [],
    requests: [],
    transactions: []
  };

  const el = (id) => document.getElementById(id);

  async function api(url, opts) {
    return FiberAuth.fetchJson(url, opts || {});
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
      const items = (req.items || []).map((i) => i.stock_item_name + ': ' + i.planned_qty).join(', ');
      return (
        '<div class="item">' +
        '<div style="display:flex;justify-content:space-between;gap:8px;">' +
        '<div class="item-title">Запит #' + String(req.id).slice(0, 8) + '</div>' +
        '<span class="pill ' + (req.status === 'fulfilled' ? 'ok' : 'warn') + '">' + req.status + '</span>' +
        '</div>' +
        '<div class="item-sub">' + (req.building_address || 'без будинку') + '</div>' +
        '<div class="item-sub">' + items + '</div>' +
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

  async function loadAll() {
    const [stock, requests, transactions] = await Promise.all([
      api('/api/stock'),
      api('/api/warehouse/requests'),
      api('/api/stock/transactions')
    ]);
    S.stock = stock || [];
    S.requests = requests || [];
    S.transactions = transactions || [];
    renderStock();
    renderRequests();
    renderTransactions();
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
    el('adjustStock')?.addEventListener('click', () => adjustStock().catch(console.error));
    el('createRequest')?.addEventListener('click', () => createRequest().catch(console.error));

    await loadAll().catch(console.error);
  }

  boot().catch(console.error);
})();
