(function () {
  'use strict';

  const BASE = '/api/network/infrastructure';
  const tbody = document.getElementById('regBody');
  const total = document.getElementById('totalCount');

  function row(building) {
    const metrics = building.panels ? (building.panels.length + ' панелей') : '—';
    return (
      '<tr>' +
      '<td>' + (building.city || '—') + '</td>' +
      '<td>' + (building.address || '—') + '</td>' +
      '<td>' + metrics + '</td>' +
      '<td><span class="status-dot" style="background:' + (building.infrastructure_status === 'completed' ? '#22c55e' : '#f59e0b') + '"></span>' + (building.infrastructure_status || '—') + '</td>' +
      '<td>' + String(building.building_id || '').slice(0, 8) + '</td>' +
      '</tr>'
    );
  }

  async function load() {
    try {
      await FiberAuth.requireAuth({ roles: ['Dispatcher'] });
      FiberAuth.bindUserBar();
    } catch (err) {
      if (err && err.message === 'forbidden-role') {
        window.location.href = FiberAuth.routeForRoles(FiberAuth.getStoredUser());
        return;
      }
      window.location.href = '/login?next=%2Fregistry';
      return;
    }

    try {
      const list = await FiberAuth.fetchJson(BASE);
      total.textContent = (list.length || 0) + ' об\'єктів';
      if (!list.length) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-muted)">Дані відсутні</td></tr>';
        return;
      }
      tbody.innerHTML = list.map(row).join('');
    } catch (err) {
      tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#f87171">Помилка завантаження: ' + err.message + '</td></tr>';
    }
  }

  load().catch(console.error);
})();
