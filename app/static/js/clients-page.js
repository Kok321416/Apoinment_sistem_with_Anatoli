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
        var rows = Array.from(document.querySelectorAll('.client-filter-row'));
        var visibleCards = [];
        var visibleCount = 0;
        var seenIds = {};

        rows.forEach(function (row) {
            var badge = row.getAttribute('data-badge') || '';
            var status = row.getAttribute('data-status') || '';
            var searchText = row.getAttribute('data-search') || '';
            var matchSearch = !q || searchText.indexOf(q) !== -1;
            var matchFilter = true;
            if (filter === 'new') matchFilter = badge === 'new';
            else if (filter === 'active') matchFilter = status === 'active';
            else if (filter === 'vip') matchFilter = badge === 'vip';
            else if (filter === 'archive') matchFilter = badge === 'inactive' || status === 'inactive';
            var show = matchSearch && matchFilter;
            row.classList.toggle('is-hidden', !show);
            if (show) {
                var id = row.getAttribute('data-id') || '';
                if (!seenIds[id]) {
                    seenIds[id] = true;
                    visibleCount += 1;
                }
                if (row.classList.contains('client-card')) visibleCards.push(row);
            }
        });

        visibleCards.sort(function (a, b) {
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
            visibleCards.forEach(function (card) {
                grid.appendChild(card);
            });
        }

        var tbody = document.getElementById('clients-table-body');
        if (tbody) {
            var tableRows = Array.from(tbody.querySelectorAll('.clients-table__row'));
            tableRows.sort(function (a, b) {
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
            tableRows.forEach(function (row) {
                tbody.appendChild(row);
            });
        }

        var empty = document.getElementById('clients-filter-empty');
        var hasSource = document.querySelectorAll('.client-filter-row').length > 0;
        if (empty) empty.hidden = visibleCount > 0 || !hasSource;
    }

    function initRelativeDates() {
        document.querySelectorAll('[data-relative]').forEach(function (el) {
            var iso = el.getAttribute('data-relative');
            if (!iso) return;
            if (el.classList.contains('client-card__meta-value') || el.getAttribute('data-relative-kind') === 'visit') {
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
