'use strict';

const warehouseState = {
  stock: [],
  requests: [],
  transactions: [],
};

function el(id) {
  return document.getElementById(id);
}

async function readJson(url, options = {}) {
  return FiberAuth.fetchJson(url, {
    ...options,
    headers: FiberAuth.getAuthHeaders(options.headers || {}),
  });
}

function renderStock(items) {
  const mount = el('stockList');
  if (!items.length) {
    mount.innerHTML = '<p class="placeholder">Склад порожній</p>';
    return;
  }
  mount.innerHTML = items.map((item) => {
    const ratio = item.min_quantity > 0 ? item.quantity / item.min_quantity : 10;
    const cls = ratio <= 0.5 ? 'bad' : ratio < 1 ? 'low' : '';
    return `
      <article class="item ${cls}">
        <p class="title">${item.name}</p>
        <p class="sub">Залишок: ${item.quantity} ${item.unit}</p>
        <p class="sub">Мінімум: ${item.min_quantity} ${item.unit}</p>
        <p class="sub">${item.shortage ? 'Дефіцит' : 'Норма'}</p>
      </article>
    `;
  }).join('');
}

function renderTransactions(items) {
  const mount = el('transactionsList');
  if (!items.length) {
    mount.innerHTML = '<p class="placeholder">Історія руху порожня</p>';
    return;
  }
  mount.innerHTML = items.map((item) => `
    <article class="item">
      <p class="title">${item.stock_item_name}</p>
      <p class="sub">Зміна: ${item.delta > 0 ? '+' : ''}${item.delta}</p>
      <p class="sub">Причина: ${item.reason || '—'}</p>
      <p class="sub">${new Date(item.created_at).toLocaleString()}</p>
    </article>
  `).join('');
}

function fillSelectOptions(selectId) {
  const select = el(selectId);
  if (!select) return;
  select.innerHTML = warehouseState.stock.map((item) => (
    `<option value="${item.id}">${item.name} · ${item.quantity} ${item.unit}</option>`
  )).join('');
}

function requestItemControls(request) {
  return request.items.map((entry) => {
    const remaining = Math.max(0, Number(entry.planned_qty) - Number(entry.fulfilled_qty || 0));
    return `
      <div class="form-box">
        <div class="sub">${entry.stock_item_name}</div>
        <div class="sub">План: ${entry.planned_qty}</div>
        <div class="sub">Видано: ${entry.fulfilled_qty || 0}</div>
        <input type="number" min="0" step="0.1" value="${remaining}" data-fulfill-item="${entry.id}">
      </div>
    `;
  }).join('');
}

function renderRequests(items) {
  const mount = el('requestList');
  if (!items.length) {
    mount.innerHTML = '<p class="placeholder">Немає відкритих запитів</p>';
    return;
  }
  mount.innerHTML = items.map((request) => `
    <article class="item">
      <p class="title">${request.building_address || 'Без адреси'}</p>
      <p class="sub">Статус: ${request.status}</p>
      <p class="sub">${request.notes || 'Без примітки'}</p>
      ${requestItemControls(request)}
      <button type="button" data-request-id="${request.id}" ${request.status === 'fulfilled' ? 'disabled' : ''}>Видати матеріали</button>
    </article>
  `).join('');

  mount.querySelectorAll('button[data-request-id]').forEach((button) => {
    button.addEventListener('click', async () => {
      const requestId = button.getAttribute('data-request-id');
      if (!requestId) return;
      const requestCard = button.closest('.item');
      const payload = Array.from(requestCard.querySelectorAll('input[data-fulfill-item]'))
        .map((input) => ({
          item_id: input.getAttribute('data-fulfill-item'),
          fulfilled_qty: Number(input.value || 0),
        }))
        .filter((entry) => entry.fulfilled_qty > 0);
      button.disabled = true;
      try {
        await readJson(`/api/warehouse/requests/${requestId}/fulfill`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ items: payload }),
        });
        await loadWarehouse();
      } catch (error) {
        console.error(error);
        button.disabled = false;
      }
    });
  });
}

async function loadWarehouse() {
  const [stock, requests, transactions] = await Promise.all([
    readJson('/api/stock'),
    readJson('/api/warehouse/requests'),
    readJson('/api/stock/transactions'),
  ]);
  warehouseState.stock = stock;
  warehouseState.requests = requests;
  warehouseState.transactions = transactions;
  renderStock(stock);
  renderRequests(requests);
  renderTransactions(transactions);
  fillSelectOptions('adjustStockItem');
  fillSelectOptions('requestStockItem');
}

function bindActions() {
  el('refreshStock').addEventListener('click', () => loadWarehouse().catch(console.error));
  el('refreshRequests').addEventListener('click', () => loadWarehouse().catch(console.error));
  el('refreshTransactions').addEventListener('click', () => loadWarehouse().catch(console.error));
  el('adjustStock').addEventListener('click', async () => {
    const stockItemId = el('adjustStockItem').value;
    const delta = Number(el('adjustDelta').value || 0);
    const reason = el('adjustReason').value.trim();
    if (!stockItemId || !delta || !reason) return;
    await readJson('/api/stock/adjust', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stock_item_id: stockItemId, delta, reason }),
    });
    el('adjustDelta').value = '';
    el('adjustReason').value = '';
    await loadWarehouse();
  });
  el('createRequest').addEventListener('click', async () => {
    const stockItemId = el('requestStockItem').value;
    const plannedQty = Number(el('requestQty').value || 0);
    const notes = el('requestNote').value.trim() || null;
    if (!stockItemId || plannedQty <= 0) return;
    await readJson('/api/warehouse/requests', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        notes,
        items: [{ stock_item_id: stockItemId, planned_qty: plannedQty }],
      }),
    });
    el('requestQty').value = '';
    el('requestNote').value = '';
    await loadWarehouse();
  });
}

async function boot() {
  try {
    await FiberAuth.requireAuth({ roles: ['Warehouse'] });
    FiberAuth.bindUserBar();
  } catch (error) {
    if (error.message === 'forbidden-role') {
      window.location.href = FiberAuth.routeForRoles(FiberAuth.getStoredUser());
      return;
    }
    throw error;
  }
  bindActions();
  try {
    await loadWarehouse();
  } catch (error) {
    console.error(error);
    el('stockList').innerHTML = '<p class="placeholder">Не вдалося завантажити склад</p>';
    el('requestList').innerHTML = '<p class="placeholder">Не вдалося завантажити заявки</p>';
    el('transactionsList').innerHTML = '<p class="placeholder">Не вдалося завантажити історію</p>';
  }
  setInterval(() => loadWarehouse().catch(console.error), 30000);
}

boot();
