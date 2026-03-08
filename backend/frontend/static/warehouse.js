'use strict';

function getAuthHeaders(extra = {}) {
  return FiberAuth.getAuthHeaders(extra);
}

function el(id) {
  return document.getElementById(id);
}

async function readJson(url, options = {}) {
  return FiberAuth.fetchJson(url, {
    ...options,
    headers: getAuthHeaders(options.headers || {}),
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

function renderRequests(items) {
  const mount = el('requestList');
  if (!items.length) {
    mount.innerHTML = '<p class="placeholder">Немає відкритих запитів</p>';
    return;
  }
  mount.innerHTML = items.map((request) => {
    const parts = request.items.map((entry) => `${entry.stock_item_name}: ${entry.planned_qty}`).join(', ');
    return `
      <article class="item">
        <p class="title">${request.building_address || 'Без адреси'}</p>
        <p class="sub">Статус: ${request.status}</p>
        <p class="sub">${parts || 'Без позицій'}</p>
        <button type="button" data-request-id="${request.id}" ${request.status === 'fulfilled' ? 'disabled' : ''}>Закрити заявку</button>
      </article>
    `;
  }).join('');

  mount.querySelectorAll('button[data-request-id]').forEach((button) => {
    button.addEventListener('click', async () => {
      const requestId = button.getAttribute('data-request-id');
      if (!requestId) {
        return;
      }
      button.disabled = true;
      try {
        await readJson(`/api/warehouse/requests/${requestId}/fulfill`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ items: [] }),
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
  const [stock, requests] = await Promise.all([
    readJson('/api/stock'),
    readJson('/api/warehouse/requests'),
  ]);
  renderStock(stock);
  renderRequests(requests);
}

function bindActions() {
  el('refreshStock').addEventListener('click', () => loadWarehouse().catch(console.error));
  el('refreshRequests').addEventListener('click', () => loadWarehouse().catch(console.error));
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
  } catch (err) {
    console.error(err);
    if (err.status === 401 || err.status === 403) {
      el('stockList').innerHTML = '<p class="placeholder">Потрібен логін комірника.</p>';
      el('requestList').innerHTML = '<p class="placeholder">Потрібен логін комірника.</p>';
    } else {
      el('stockList').innerHTML = '<p class="placeholder">Не вдалося завантажити /api/stock</p>';
      el('requestList').innerHTML = '<p class="placeholder">Не вдалося завантажити /api/warehouse/requests</p>';
    }
  }
  setInterval(() => loadWarehouse().catch(console.error), 30000);
}

boot();
