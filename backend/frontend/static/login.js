'use strict';

function el(id) {
  return document.getElementById(id);
}

async function boot() {
  const existing = await FiberAuth.loadCurrentUser();
  if (existing) {
    window.location.href = FiberAuth.routeForRoles(existing);
    return;
  }

  const form = el('loginForm');
  const status = el('loginStatus');
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    status.textContent = 'Вхід...';
    status.className = 'status';
    try {
      const user = await FiberAuth.login(el('phone').value.trim(), el('password').value);
      status.textContent = `Успішно: ${user.name}`;
      status.className = 'status ok';
      const next = new URLSearchParams(window.location.search).get('next');
      window.location.href = next || FiberAuth.routeForRoles(user);
    } catch (error) {
      console.error(error);
      status.textContent = error.status === 401 ? 'Невірний логін або пароль' : `Помилка входу: ${error.message}`;
      status.className = 'status error';
    }
  });
}

boot().catch(console.error);
