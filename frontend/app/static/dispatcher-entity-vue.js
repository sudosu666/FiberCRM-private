(function () {
  'use strict';

  if (!window.Vue) return;
  var mount = document.getElementById('entityDetailsApp');
  if (!mount) return;

  var app = window.Vue.createApp({
    data: function () {
      return {
        tasks: [],
        buildings: [],
        brigades: [],
        workers: [],
        selectedType: '',
        selectedId: ''
      };
    },
    computed: {
      selectedTask: function () {
        if (this.selectedType !== 'task') return null;
        return this.tasks.find(function (item) { return String(item.id) === String(this.selectedId); }, this) || null;
      },
      selectedBuilding: function () {
        if (this.selectedType !== 'building') return null;
        return this.buildings.find(function (item) { return String(item.id) === String(this.selectedId); }, this) || null;
      },
      selectedWorker: function () {
        if (this.selectedType !== 'worker') return null;
        return this.workers.find(function (item) { return String(item.id) === String(this.selectedId); }, this) || null;
      },
      selectedBrigade: function () {
        if (this.selectedType !== 'brigade') return null;
        return this.brigades.find(function (item) { return String(item.id) === String(this.selectedId); }, this) || null;
      }
    },
    methods: {
      statusLabel: function (status) {
        var labels = {
          pending: 'Очікування',
          assigned: 'Призначено',
          in_progress: 'В роботі',
          completed: 'Виконано',
          canceled: 'Скасовано',
          on_hold: 'Пауза'
        };
        return labels[status] || status || '—';
      },
      setData: function (payload) {
        this.tasks = Array.isArray(payload.tasks) ? payload.tasks : [];
        this.buildings = Array.isArray(payload.buildings) ? payload.buildings : [];
        this.brigades = Array.isArray(payload.brigades) ? payload.brigades : [];
        this.workers = Array.isArray(payload.workers) ? payload.workers : [];
      },
      selectEntity: function (entityType, entityId) {
        this.selectedType = entityType || '';
        this.selectedId = entityId || '';
      }
    },
    template:
      '<div>' +
      '<div v-if="!selectedType" style="color:var(--text-secondary)">' +
      'Оберіть будинок, співробітника або задачу для детального перегляду.' +
      '</div>' +

      '<div v-else-if="selectedType === \'task\' && selectedTask">' +
      '<div><strong>Задача</strong></div>' +
      '<div>ID: {{ selectedTask.id }}</div>' +
      '<div>Адреса: {{ selectedTask.building_address || "—" }}</div>' +
      '<div>Статус: {{ statusLabel(selectedTask.status) }}</div>' +
      '<div>Бригада: {{ selectedTask.brigade_name || "—" }}</div>' +
      '<div>Пріоритет: {{ selectedTask.priority ?? "—" }}</div>' +
      '<div>Опис: {{ selectedTask.description || "—" }}</div>' +
      '</div>' +

      '<div v-else-if="selectedType === \'building\' && selectedBuilding">' +
      '<div><strong>Будинок</strong></div>' +
      '<div>ID: {{ selectedBuilding.id }}</div>' +
      '<div>Адреса: {{ selectedBuilding.address || "—" }}</div>' +
      '<div>Місто: {{ selectedBuilding.city || "—" }}</div>' +
      '<div>Під\'їзди: {{ selectedBuilding.entrances_count || 0 }}</div>' +
      '<div>Поверхи: {{ selectedBuilding.floors_count || 0 }}</div>' +
      '<div>Статус інфри: {{ selectedBuilding.infrastructure_status || "—" }}</div>' +
      '</div>' +

      '<div v-else-if="selectedType === \'worker\' && selectedWorker">' +
      '<div><strong>Співробітник</strong></div>' +
      '<div>ID: {{ selectedWorker.id }}</div>' +
      '<div>ПІБ: {{ selectedWorker.name || "—" }}</div>' +
      '<div>Телефон: {{ selectedWorker.phone || "—" }}</div>' +
      '<div>Роль: {{ selectedWorker.role || "—" }}</div>' +
      '<div>Бригада: {{ selectedWorker.brigade_name || "—" }}</div>' +
      '</div>' +

      '<div v-else-if="selectedType === \'brigade\' && selectedBrigade">' +
      '<div><strong>Бригада</strong></div>' +
      '<div>ID: {{ selectedBrigade.id }}</div>' +
      '<div>Назва: {{ selectedBrigade.name || "—" }}</div>' +
      '<div>Тип: {{ selectedBrigade.type || "—" }}</div>' +
      '<div>Статус: {{ selectedBrigade.status_label || "—" }}</div>' +
      '<div>Учасників: {{ selectedBrigade.members || 0 }}</div>' +
      '<div>Активна: {{ selectedBrigade.is_active ? "так" : "ні" }}</div>' +
      '</div>' +

      '<div v-else>Сутність не знайдена або не підтримується.</div>' +
      '</div>'
  });

  var vm = app.mount('#entityDetailsApp');
  window.DispatcherEntityBridge = {
    setData: function (payload) {
      if (vm && typeof vm.setData === 'function') vm.setData(payload || {});
    },
    selectEntity: function (entityType, entityId) {
      if (vm && typeof vm.selectEntity === 'function') vm.selectEntity(entityType, entityId);
      return true;
    }
  };
})();
