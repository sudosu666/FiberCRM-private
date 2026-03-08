'use strict';

const state = {
  tenders: [],
  stock: [],
  muffles: [],
  selectedMuffleId: null,
  selectedFibers: [],
  calc: null,
};

function el(id) { return document.getElementById(id); }

async function readJson(url, options) {
  return FiberAuth.fetchJson(url, options || {});
}

function calculateNeeds() {
  const entrances = Number(el('entrances').value) || 0;
  const floors = Number(el('floors').value) || 0;
  const flats = Number(el('flats').value) || 0;
  const floorHeight = Number(el('floorHeight').value) || 0;
  const panelEvery = Math.max(1, Number(el('panelEvery').value) || 1);
  const distance = Number(el('distance').value) || 0;
  const reserve = Number(el('reserve').value) || 0;

  const panels = entrances * Math.ceil(floors / panelEvery);
  const clients = entrances * floors * flats;
  const inner = entrances * floors * floorHeight;
  const totalCable = Math.ceil((inner + distance) * (1 + reserve / 100));
  const patches = panels * 8;
  state.calc = { panels, clients, totalCable, patches };
  renderCalc();
}

function renderCalc() {
  const mount = el('calcView');
  const c = state.calc;
  if (!c) {
    mount.innerHTML = '<p class="placeholder">Натисни «Перерахувати»</p>';
    return;
  }
  const cableStock = state.stock.find((item) => item.name.toLowerCase().includes('кабель'));
  const panelStock = state.stock.find((item) => item.name.toLowerCase().includes('щит'));
  const muffleStock = state.stock.find((item) => item.name.toLowerCase().includes('муфта'));
  const cableDiff = cableStock ? cableStock.quantity - c.totalCable : null;
  const panelDiff = panelStock ? panelStock.quantity - c.panels : null;
  const muffleDiff = muffleStock ? muffleStock.quantity - 1 : null;

  mount.innerHTML = `
    <article class="item">
      <p class="title">Щитки: ${c.panels} шт.</p>
      <p class="sub">Клієнти: ${c.clients}</p>
      <p class="sub">Кабель загалом: ${c.totalCable} м</p>
      <p class="sub">Патч-корди: ${c.patches} шт.</p>
    </article>
    <article class="item">
      <p class="title">Склад</p>
      <p class="sub ${cableDiff !== null && cableDiff < 0 ? 'warn' : ''}">Кабель: ${cableStock ? cableStock.quantity : 'н/д'} (потрібно ${c.totalCable})</p>
      <p class="sub ${panelDiff !== null && panelDiff < 0 ? 'warn' : ''}">Щитки: ${panelStock ? panelStock.quantity : 'н/д'} (потрібно ${c.panels})</p>
      <p class="sub ${muffleDiff !== null && muffleDiff < 0 ? 'warn' : ''}">Муфти: ${muffleStock ? muffleStock.quantity : 'н/д'} (потрібно 1)</p>
    </article>
  `;
}

function toggleFiber(muffleId, fiberNumber, busy) {
  if (busy) {
    return;
  }
  if (state.selectedMuffleId !== muffleId) {
    state.selectedMuffleId = muffleId;
    state.selectedFibers = [];
  }
  const idx = state.selectedFibers.indexOf(fiberNumber);
  if (idx >= 0) {
    state.selectedFibers.splice(idx, 1);
  } else {
    state.selectedFibers.push(fiberNumber);
  }
  renderMuffles();
}

function renderMuffles() {
  const mount = el('mufflesList');
  if (!state.muffles.length) {
    mount.innerHTML = '<p class="placeholder">Муфти не знайдені</p>';
    return;
  }
  mount.innerHTML = state.muffles.map((muffle) => {
    const selected = muffle.id === state.selectedMuffleId;
    const fibers = muffle.fibers.map((fiber) => {
      const busy = fiber.status !== 'free';
      const picked = selected && state.selectedFibers.includes(fiber.fiber_number);
      const classes = ['fiber', busy ? 'busy' : 'free', picked ? 'selected' : ''].join(' ');
      return `<button type="button" class="${classes}" data-mid="${muffle.id}" data-fn="${fiber.fiber_number}" data-busy="${busy ? '1' : '0'}">${fiber.fiber_number}</button>`;
    }).join('');
    return `
      <article class="item">
        <p class="title">${muffle.name || 'Муфта'}</p>
        <p class="sub">${muffle.address_note || 'Без опису'}</p>
        <p class="sub">Місткість: ${muffle.capacity}</p>
        <div class="fibers">${fibers}</div>
      </article>
    `;
  }).join('');

  mount.querySelectorAll('button[data-mid]').forEach((btn) => {
    btn.addEventListener('click', () => {
      toggleFiber(
        btn.getAttribute('data-mid'),
        Number(btn.getAttribute('data-fn')),
        btn.getAttribute('data-busy') === '1',
      );
    });
  });
}

function renderTenders() {
  const select = el('tenderId');
  select.innerHTML = state.tenders.map((tender) => `<option value="${tender.id}">${tender.name}</option>`).join('');
}

async function loadInitial() {
  const [tenders, stock, muffles] = await Promise.all([
    readJson('/api/tenders'),
    readJson('/api/stock'),
    readJson('/api/network/topology'),
  ]);
  state.tenders = tenders;
  state.stock = stock;
  state.muffles = muffles;
  renderTenders();
  renderMuffles();
  calculateNeeds();
}

function collectPayload() {
  return {
    tender_id: el('tenderId').value || null,
    address: el('address').value.trim(),
    city: el('city').value.trim() || null,
    entrances_count: Number(el('entrances').value),
    floors_count: Number(el('floors').value),
    flats_per_floor: Number(el('flats').value),
    floor_height_m: Number(el('floorHeight').value),
    panel_every_n_floors: Number(el('panelEvery').value),
    distance_from_muffle_m: Number(el('distance').value),
    cable_reserve_pct: Number(el('reserve').value),
    muffle_id: state.selectedMuffleId,
    selected_fibers: [...state.selectedFibers],
  };
}

async function savePlan() {
  const resultEl = el('saveResult');
  const payload = collectPayload();
  if (!payload.address) {
    resultEl.textContent = 'Адреса обовʼязкова';
    resultEl.className = 'result warn';
    return;
  }
  resultEl.textContent = 'Збереження...';
  resultEl.className = 'result';
  try {
    const result = await readJson('/api/network/plan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    resultEl.textContent = `Готово: building=${result.building_id}, tasks=${result.task_ids.length}, warehouse=${result.warehouse_request_id || 'none'}`;
    resultEl.className = 'result';
  } catch (err) {
    console.error(err);
    resultEl.textContent = `Помилка: ${err.message}`;
    resultEl.className = 'result warn';
  }
}

function boot() {
  FiberAuth.requireAuth({ roles: ['Designer', 'Dispatcher'] })
    .then(() => FiberAuth.bindUserBar())
    .catch((error) => {
      if (error.message === 'forbidden-role') {
        window.location.href = FiberAuth.routeForRoles(FiberAuth.getStoredUser());
        return;
      }
      throw error;
    });
  el('calcBtn').addEventListener('click', calculateNeeds);
  el('saveBtn').addEventListener('click', savePlan);
  ['entrances', 'floors', 'flats', 'floorHeight', 'panelEvery', 'distance', 'reserve']
    .forEach((id) => el(id).addEventListener('input', calculateNeeds));

  loadInitial().catch((err) => {
    console.error(err);
    el('mufflesList').innerHTML = '<p class="placeholder">Помилка завантаження /api/network/topology</p>';
    el('calcView').innerHTML = '<p class="placeholder">Помилка завантаження /api/stock</p>';
  });
}

boot();
