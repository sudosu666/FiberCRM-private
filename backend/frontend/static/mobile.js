const state = {
  tasks: [],
  currentTaskId: null,
  steps: [],
  photos: [],
  chatMessages: [],
  brigadeId: 'BRG-03',
  brigadeName: 'Бригада BRG-03',
};

const qs = (selector) => document.querySelector(selector);
const qsa = (selector) => Array.from(document.querySelectorAll(selector));

const taskList = qs('#taskList');
const stepTimeline = qs('#stepTimeline');
const stepBadge = qs('#stepBadge');
const syncStatus = qs('#syncStatus');
const chatWindow = qs('#chatWindow');
const chatForm = qs('#chatForm');
const chatInput = qs('#chatInput');
const phaseTabs = qsa('.phase-tab');
const signalStrength = qs('#signalStrength');
const chatStatus = qs('#chatStatus');

let socket;
let socketConnected = false;
const PHOTO_TARGET_BYTES = 200 * 1024;
const PHOTO_FALLBACK_QUALITY = 0.25;
const DB_NAME = 'fiberops-offline';
const DB_STORE = 'queue';

function openQueueDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      req.result.createObjectStore(DB_STORE, { keyPath: 'id', autoIncrement: true });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function enqueueAction(action) {
  const db = await openQueueDb();
  await new Promise((resolve, reject) => {
    const tx = db.transaction(DB_STORE, 'readwrite');
    tx.objectStore(DB_STORE).add({ ...action, queuedAt: Date.now() });
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  db.close();
}

async function flushQueue() {
  if (!navigator.onLine) return;
  const db = await openQueueDb();
  const rows = await new Promise((resolve, reject) => {
    const tx = db.transaction(DB_STORE, 'readonly');
    const req = tx.objectStore(DB_STORE).getAll();
    req.onsuccess = () => resolve(req.result || []);
    req.onerror = () => reject(req.error);
  });
  for (const row of rows) {
    try {
      if (row.kind === 'step') {
        await fetch(`/api/tasks/${row.taskId}/steps/${row.stepId}/complete`, { method: 'PATCH' });
      } else if (row.kind === 'photo') {
        await persistPhotoReportInternal(row.filename, row.dataUrl, row.comment, true);
      } else if (row.kind === 'chat' && socketConnected) {
        socket?.emit('chat.message', row.payload);
      }
      await new Promise((resolve, reject) => {
        const tx = db.transaction(DB_STORE, 'readwrite');
        tx.objectStore(DB_STORE).delete(row.id);
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
      });
    } catch (error) {
      console.warn('flush queue failed', error);
      break;
    }
  }
  db.close();
}

function dataUrlSizeBytes(dataUrl) {
  const payload = dataUrl.split(',')[1] ?? '';
  return Math.floor((payload.length * 3) / 4);
}

async function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

async function compressPhotoFile(file) {
  const sourceDataUrl = await readFileAsDataUrl(file);
  if (typeof sourceDataUrl !== 'string') {
    return { dataUrl: null, filename: file.name };
  }
  if (!file.type.startsWith('image/')) {
    return { dataUrl: sourceDataUrl, filename: file.name };
  }

  const image = await new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = sourceDataUrl;
  });

  const canvas = document.createElement('canvas');
  canvas.width = image.width;
  canvas.height = image.height;
  const ctx = canvas.getContext('2d');
  if (!ctx) {
    return { dataUrl: sourceDataUrl, filename: file.name };
  }
  ctx.drawImage(image, 0, 0);

  let quality = 0.85;
  let best = canvas.toDataURL('image/jpeg', quality);
  while (dataUrlSizeBytes(best) > PHOTO_TARGET_BYTES && quality > PHOTO_FALLBACK_QUALITY) {
    quality = Math.max(PHOTO_FALLBACK_QUALITY, quality - 0.1);
    best = canvas.toDataURL('image/jpeg', quality);
    if (quality === PHOTO_FALLBACK_QUALITY) {
      break;
    }
  }

  const safeName = file.name.replace(/\.[^.]+$/, '') || 'photo';
  return { dataUrl: best, filename: `${safeName}.jpg` };
}

async function loadTasks() {
  try {
    const response = await fetch('/api/tasks');
    if (!response.ok) throw new Error('API error');
    const payload = await response.json();
    state.tasks = payload;
    state.currentTaskId = payload[0]?.id ?? null;
    renderTasks();
    await loadTaskSteps();
    syncStatus.textContent = `Синхронізовано: ${new Date().toLocaleTimeString()}`;
  } catch (error) {
    taskList.innerHTML = '<div class="placeholder">Не вдалося отримати задачі. Спробуйте ще раз.</div>';
    console.warn('Fetch tasks failed', error);
  }
}

async function loadTaskSteps() {
  if (!state.currentTaskId) {
    state.steps = [];
    renderSteps();
    return;
  }
  try {
    const response = await fetch(`/api/tasks/${state.currentTaskId}/steps`);
    if (!response.ok) throw new Error('steps api error');
    const steps = await response.json();
    state.steps = steps.map((step) => ({
      id: step.id,
      title: step.title,
      desc: step.hint || 'Крок без опису',
      eta: step.is_done ? 'done' : 'pending',
      status: step.is_done ? 'completed' : 'pending',
    }));
    renderSteps();
  } catch (error) {
    console.warn('load steps failed', error);
    if (!state.steps.length) {
      state.steps = [
        { title: 'Прийом завдання', desc: 'Диспетчер підтвердив і призначив бригаду.', eta: '2 хв', status: 'pending' },
        { title: 'Виїзд на об\'єкт', desc: 'Бригада прибуває, перевіряє доступ.', eta: '10 хв', status: 'pending' },
      ];
      renderSteps();
    }
  }
}

function renderTasks() {
  if (!state.tasks.length) {
    taskList.innerHTML = '<div class="placeholder">Список задач порожній.</div>';
    return;
  }

  taskList.innerHTML = '';
  state.tasks.forEach((task) => {
    const card = document.createElement('button');
    card.type = 'button';
    card.className = 'task-card';
    if (task.id === state.currentTaskId) {
      card.classList.add('active');
    }
    card.innerHTML = `
      <strong>${task.type ?? 'Task'}</strong>
      <span class="secondary">${task.building_address ?? 'Адреса невідома'}</span>
      <span class="secondary">${task.description ?? 'Опис недоступний'}</span>
      <small class="secondary">Статус: ${task.status}</small>
    `;
    card.addEventListener('click', () => {
      state.currentTaskId = task.id;
      renderTasks();
      loadTaskSteps();
    });
    taskList.appendChild(card);
  });
}

function renderSteps() {
  stepTimeline.innerHTML = '';
  const nextPending = state.steps.findIndex((step) => step.status === 'pending');
  const activeIndex = nextPending === -1 ? state.steps.length - 1 : Math.max(0, nextPending);
  state.steps.forEach((step, index) => {
    const card = document.createElement('article');
    card.className = 'step-card';
    if (index <= activeIndex) {
      card.classList.add('active');
    }
    card.innerHTML = `
      <strong>Крок ${index + 1}: ${step.title}</strong>
      <p>${step.desc}</p>
      <small class="secondary">ETA: ${step.eta}</small>
    `;
    stepTimeline.appendChild(card);
  });
  stepBadge.textContent = `Крок ${Math.min(state.steps.length, activeIndex + 1)} з ${state.steps.length}`;
}

function advanceStep() {
  const nextStep = state.steps.findIndex((step) => step.status === 'pending');
  if (nextStep === -1) return;
  state.steps[nextStep].status = 'completed';
  renderSteps();
  const stepId = state.steps[nextStep].id;
  if (stepId && state.currentTaskId) {
    fetch(`/api/tasks/${state.currentTaskId}/steps/${stepId}/complete`, { method: 'PATCH' })
      .catch(async () => {
        await enqueueAction({ kind: 'step', taskId: state.currentTaskId, stepId });
      });
  }
  socket?.emit('progress.update', {
    brigade_id: state.brigadeId,
    brigade_name: state.brigadeName,
    step: state.steps[nextStep].title,
    task_id: state.currentTaskId,
    timestamp: new Date().toISOString(),
  });
}

function renderPhotos() {
  if (!state.photos.length) {
    qs('#photoGrid').innerHTML = '<div class="placeholder">Фото ще немає</div>';
    return;
  }
  const grid = qs('#photoGrid');
  grid.innerHTML = '';
  state.photos.forEach((photo) => {
    const card = document.createElement('div');
    card.className = 'photo-card';
    card.innerHTML = `
      <img alt="${photo.name}" src="${photo.url}">
      <span>${photo.label}</span>
    `;
    grid.appendChild(card);
  });
}

function handlePhotoUpload(event) {
  const files = Array.from(event.target.files);
  files.forEach(async (file) => {
    try {
      const { dataUrl, filename } = await compressPhotoFile(file);
      if (typeof dataUrl !== 'string') return;
      const label = new Date().toLocaleTimeString();
      state.photos.unshift({ name: filename, url: dataUrl, label });
      renderPhotos();
      persistPhotoReport(filename, dataUrl, label);
    } catch (error) {
      console.warn('photo compression failed', error);
    }
  });
  event.target.value = '';
}

async function persistPhotoReport(filename, dataUrl, comment) {
  return persistPhotoReportInternal(filename, dataUrl, comment, false);
}

async function persistPhotoReportInternal(filename, dataUrl, comment, fromQueue = false) {
  if (!state.currentTaskId) return;
  try {
    await fetch(`/api/tasks/${state.currentTaskId}/reports`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        photo_filename: filename,
        photo_data: dataUrl,
        comment,
        brigade_id: state.brigadeId,
        brigade_name: state.brigadeName,
      }),
    });
  } catch (error) {
    console.warn('failed to persist photo report', error);
    if (!fromQueue) {
      await enqueueAction({ kind: 'photo', taskId: state.currentTaskId, filename, dataUrl, comment });
    }
  }
}

function connectChat() {
  socket = io({
    auth: { role: 'Builder', brigade_id: state.brigadeId, brigade_name: state.brigadeName },
    transports: ['websocket'],
  });

  socket.on('connect', () => {
    socketConnected = true;
    chatStatus.textContent = 'online';
    chatStatus.style.background = 'rgba(61, 220, 151, 0.2)';
    chatStatus.style.borderColor = 'rgba(61, 220, 151, 0.4)';
    flushQueue().catch((error) => console.warn('queue flush failed', error));
  });

  socket.on('disconnect', () => {
    socketConnected = false;
    chatStatus.textContent = 'offline';
    chatStatus.style.background = 'transparent';
    chatStatus.style.borderColor = 'var(--border)';
  });

  socket.on('chat.message', (payload) => {
    appendChatMessage(payload);
  });
}

function appendChatMessage(payload, isSelf = false) {
  const wrapper = document.createElement('div');
  wrapper.className = `chat-message${isSelf ? ' self' : ''}`;
  const timestamp = payload.timestamp ? new Date(payload.timestamp) : new Date();
  const user = payload.user ?? 'Диспетчер';
  wrapper.innerHTML = `
    <strong>${user}</strong>
    <span>${payload.message}</span>
    <small class="secondary">${timestamp.toLocaleTimeString()}</small>
  `;
  chatWindow.querySelector('.placeholder')?.remove();
  chatWindow.appendChild(wrapper);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function setupChatForm() {
  chatForm.addEventListener('submit', (event) => {
    event.preventDefault();
    const message = chatInput.value.trim();
    if (!message) return;
    const payload = {
      brigade_id: state.brigadeId,
      brigade_name: state.brigadeName,
      user: state.brigadeName,
      task_id: state.currentTaskId,
      message,
      timestamp: new Date().toISOString(),
    };
    socket?.emit('chat.message', payload);
    if (!socketConnected) {
      enqueueAction({ kind: 'chat', payload }).catch((error) => console.warn('queue chat failed', error));
    }
    appendChatMessage(payload, true);
    chatInput.value = '';
  });
}

function bindPhaseNav() {
  phaseTabs.forEach((tab) => {
    tab.addEventListener('click', () => {
      qsa('.phase-tab').forEach((btn) => btn.classList.remove('is-active'));
      tab.classList.add('is-active');
      const target = document.getElementById(tab.dataset.target);
      target?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });
}

function registerServiceWorker() {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/static/sw.js').catch((err) => {
      console.warn('Service worker registration failed', err);
    });
  }
}

function updateSignalStrength() {
  const status = navigator.onLine ? '🛰️ Онлайн' : '⚠️ Офлайн';
  signalStrength.textContent = status;
}

window.addEventListener('DOMContentLoaded', () => {
  bindPhaseNav();
  qs('#refreshTasks')?.addEventListener('click', loadTasks);
  qs('#photoInput').addEventListener('change', handlePhotoUpload);
  qs('#addPhotoButton').addEventListener('click', () => qs('#photoInput').click());
  qs('#advanceStep').addEventListener('click', advanceStep);
  setupChatForm();
  registerServiceWorker();
  loadTasks();
  renderSteps();
  renderPhotos();
  connectChat();
  updateSignalStrength();
  flushQueue().catch((error) => console.warn('initial queue flush failed', error));
  window.addEventListener('online', updateSignalStrength);
  window.addEventListener('online', () => flushQueue().catch((error) => console.warn('online queue flush failed', error)));
  window.addEventListener('offline', updateSignalStrength);
});
