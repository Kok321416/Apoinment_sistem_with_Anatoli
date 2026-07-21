(function (global) {
    function formatRelative(iso) {
        if (!iso) return '—';
        try {
            var d = new Date(iso);
            var diff = Date.now() - d.getTime();
            var mins = Math.floor(diff / 60000);
            if (mins < 1) return 'только что';
            if (mins < 60) return mins + ' мин. назад';
            var hours = Math.floor(mins / 60);
            if (hours < 24) return hours + ' ч. назад';
            var days = Math.floor(hours / 24);
            if (days === 1) return 'вчера';
            if (days < 7) return days + ' дн. назад';
            return d.toLocaleDateString('ru-RU');
        } catch (e) {
            return iso;
        }
    }

    function formatRelativeFuture(iso) {
        if (!iso) return 'Нет записей';
        try {
            var d = new Date(iso + 'T12:00:00');
            var today = new Date();
            today.setHours(0, 0, 0, 0);
            var diff = today - d;
            var days = Math.floor(diff / 86400000);
            if (days === 0) return 'сегодня';
            if (days === 1) return 'вчера';
            if (days < 7) return days + ' дн. назад';
            if (days < 30) return Math.floor(days / 7) + ' нед. назад';
            return d.toLocaleDateString('ru-RU');
        } catch (e) {
            return iso;
        }
    }

    function loadData() {
        var node = document.getElementById('clients-crm-data');
        if (!node) return { clients: [], dashboard: {}, activity: [] };
        try {
            return JSON.parse(node.textContent || '{}');
        } catch (e) {
            return { clients: [], dashboard: {}, activity: [] };
        }
    }

    function openCreateForm() {
        var panel = document.getElementById('clients-create');
        if (panel) {
            panel.hidden = false;
            var nameInput = document.getElementById('name');
            if (nameInput) nameInput.focus();
        }
    }

    function closeCreateForm() {
        var panel = document.getElementById('clients-create');
        if (panel) panel.hidden = true;
    }

    function exportCsv(clients) {
        var rows = [['Имя', 'Телефон', 'Email', 'Telegram', 'Заметки', 'Записей', 'Заполненность']];
        clients.forEach(function (c) {
            rows.push([
                c.name || '',
                c.phone || '',
                c.email || '',
                c.telegram || '',
                (c.notes || '').replace(/\n/g, ' '),
                String(c.booking_count || 0),
                String((c.completeness && c.completeness.percent) || 0) + '%',
            ]);
        });
        var csv = rows.map(function (row) {
            return row.map(function (cell) {
                var s = String(cell);
                if (/[",;\n]/.test(s)) return '"' + s.replace(/"/g, '""') + '"';
                return s;
            }).join(';');
        }).join('\n');
        var blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' });
        var a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'clients-' + new Date().toISOString().slice(0, 10) + '.csv';
        a.click();
        URL.revokeObjectURL(a.href);
    }

    function contactUrl(client) {
        if (client.telegram) {
            var t = client.telegram.replace('@', '').trim();
            if (t.indexOf('http') === 0) return t;
            return 'https://t.me/' + t.split('/').pop();
        }
        if (client.phone) return 'tel:' + client.phone.replace(/\s/g, '');
        if (client.email) return 'mailto:' + client.email;
        return null;
    }

    function filterCards() {
        var search = (document.getElementById('clients-search') || {}).value || '';
        var filter = (document.getElementById('clients-filter') || {}).value || 'all';
        var sort = (document.getElementById('clients-sort') || {}).value || 'recent';
        var q = search.trim().toLowerCase();
        var cards = Array.from(document.querySelectorAll('.client-card'));
        var visible = [];

        cards.forEach(function (card) {
            var badge = card.getAttribute('data-badge') || '';
            var status = card.getAttribute('data-status') || '';
            var searchText = card.getAttribute('data-search') || '';
            var matchSearch = !q || searchText.indexOf(q) !== -1;
            var matchFilter = true;
            if (filter === 'new') matchFilter = badge === 'new';
            else if (filter === 'active') matchFilter = status === 'active';
            else if (filter === 'vip') matchFilter = badge === 'vip';
            else if (filter === 'archive') matchFilter = badge === 'inactive' || status === 'inactive';
            var show = matchSearch && matchFilter;
            card.classList.toggle('is-hidden', !show);
            if (show) visible.push(card);
        });

        visible.sort(function (a, b) {
            if (sort === 'name') {
                return (a.getAttribute('data-name') || '').localeCompare(b.getAttribute('data-name') || '', 'ru');
            }
            if (sort === 'created') {
                return (b.getAttribute('data-created') || '').localeCompare(a.getAttribute('data-created') || '');
            }
            if (sort === 'last_visit') {
                return (b.getAttribute('data-last-visit') || '').localeCompare(a.getAttribute('data-last-visit') || '');
            }
            return (b.getAttribute('data-updated') || '').localeCompare(a.getAttribute('data-updated') || '');
        });

        var grid = document.getElementById('clients-grid');
        if (grid) {
            visible.forEach(function (card) {
                grid.appendChild(card);
            });
        }

        var empty = document.getElementById('clients-filter-empty');
        if (empty) empty.hidden = visible.length > 0 || cards.length === 0;
    }

    function initRelativeDates() {
        document.querySelectorAll('[data-relative]').forEach(function (el) {
            var iso = el.getAttribute('data-relative');
            if (!iso) return;
            if (el.classList.contains('client-card__meta-value')) {
                el.textContent = formatRelativeFuture(iso);
            } else {
                el.textContent = formatRelative(iso);
            }
        });
    }

    function initHero(dashboard) {
        var updated = document.getElementById('hero-updated');
        if (updated && dashboard.last_updated) {
            updated.textContent = 'Последнее изменение: ' + formatRelative(dashboard.last_updated);
        } else if (updated && dashboard.last_created) {
            updated.textContent = 'Последнее добавление: ' + formatRelative(dashboard.last_created);
        }
    }

    function init() {
        var page = document.getElementById('clients-page');
        if (!page) return;

        var data = loadData();
        initHero(data.dashboard || {});
        initRelativeDates();

        document.getElementById('btn-add-client') && document.getElementById('btn-add-client').addEventListener('click', openCreateForm);
        document.getElementById('btn-empty-add') && document.getElementById('btn-empty-add').addEventListener('click', openCreateForm);
        document.getElementById('btn-close-create') && document.getElementById('btn-close-create').addEventListener('click', closeCreateForm);

        document.getElementById('btn-export-clients') && document.getElementById('btn-export-clients').addEventListener('click', function () {
            exportCsv(data.clients || []);
            if (global.showToast) global.showToast('Экспорт завершён');
        });

        document.getElementById('btn-import-clients') && document.getElementById('btn-import-clients').addEventListener('click', function () {
            if (global.showToast) global.showToast('Импорт будет доступен в следующей версии', 'info');
        });

        var search = document.getElementById('clients-search');
        var filterEl = document.getElementById('clients-filter');
        var sortEl = document.getElementById('clients-sort');
        if (search) search.addEventListener('input', filterCards);
        if (filterEl) filterEl.addEventListener('change', filterCards);
        if (sortEl) sortEl.addEventListener('change', filterCards);

        document.querySelectorAll('[data-action="message"]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var card = btn.closest('.client-card');
                if (!card) return;
                var id = parseInt(card.getAttribute('data-id'), 10);
                var client = (data.clients || []).find(function (c) { return c.id === id; });
                if (!client) return;
                var url = contactUrl(client);
                if (url) window.open(url, '_blank');
            });
        });

        if (global.clientDrawer) {
            global.clientDrawer.init(data.clients || []);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})(window);
