(function () {
    const PAGE_SIZE = 6;

    function init() {
        const page = document.getElementById('services-page');
        if (!page) return;

        const csrf = page.dataset.csrf || '';
        const api = new ServicesApi(csrf);
        let catalog = null;
        let filtered = [];
        let currentPage = 1;
        let viewMode = 'grid';
        let selectedIds = new Set();
        let openMenuId = null;

        const grid = document.getElementById('services-grid');
        const loading = document.getElementById('services-loading');
        const empty = document.getElementById('services-empty');
        const pagination = document.getElementById('services-pagination');
        const bulkBar = document.getElementById('services-bulk-bar');

        const drawer = new ServiceDrawer({
            api: api,
            onSaved: applyCatalog,
        });

        document.getElementById('btn-new-service').addEventListener('click', () => {
            if (!catalog) {
                if (typeof showToast === 'function') showToast('Каталог ещё загружается…');
                return;
            }
            drawer.openCreate(catalog.calendars, catalog.templates);
        });
        document.getElementById('btn-empty-create').addEventListener('click', () => {
            if (!catalog) {
                if (typeof showToast === 'function') showToast('Каталог ещё загружается…');
                return;
            }
            drawer.openCreate(catalog.calendars, catalog.templates);
        });

        document.getElementById('services-search').addEventListener('input', () => {
            currentPage = 1;
            render();
        });
        document.getElementById('filter-status').addEventListener('change', () => {
            currentPage = 1;
            render();
        });
        document.getElementById('sort-by').addEventListener('change', () => {
            currentPage = 1;
            render();
        });

        document.querySelectorAll('.view-toggle__btn').forEach((btn) => {
            btn.addEventListener('click', () => {
                viewMode = btn.dataset.view;
                document.querySelectorAll('.view-toggle__btn').forEach((b) => {
                    b.classList.toggle('is-active', b === btn);
                });
                grid.classList.toggle('services-grid--list', viewMode === 'list');
                render();
            });
        });

        document.querySelectorAll('[data-bulk]').forEach((btn) => {
            btn.addEventListener('click', () => bulkAction(btn.dataset.bulk));
        });
        document.getElementById('bulk-clear').addEventListener('click', () => {
            selectedIds.clear();
            updateBulkBar();
            render();
        });

        document.addEventListener('click', () => closeMenus());

        async function load() {
            page.classList.add('is-loading');
            try {
                catalog = await api.getCatalog();
                applyCatalog(catalog);
            } catch (error) {
                loading.textContent = 'Не удалось загрузить услуги: ' + error.message;
                showToast(error.message, 'error');
            } finally {
                page.classList.remove('is-loading');
            }
        }

        function applyCatalog(data) {
            catalog = data;
            updateDashboard(data.dashboard);
            updateAnalytics(data.analytics);
            currentPage = 1;
            filterAndRender();
        }

        function updateDashboard(d) {
            document.querySelector('[data-stat="total"]').textContent = d.total;
            document.querySelector('[data-stat="active"]').textContent = d.active;
            document.querySelector('[data-stat="avg_duration"]').textContent = d.avg_duration ? d.avg_duration + ' мин' : '—';
            document.querySelector('[data-stat="calendars_used"]').textContent = d.calendars_used;
        }

        function updateAnalytics(a) {
            document.querySelector('[data-analytics="total_bookings"]').textContent = a.total_bookings;
            document.querySelector('[data-analytics="fill_rate"]').textContent = a.fill_rate + '%';
            document.querySelector('[data-analytics="avg_price"]').textContent = a.avg_price ? a.avg_price + ' ₽' : '—';
            document.querySelector('[data-analytics="avg_duration"]').textContent = a.avg_duration ? a.avg_duration + ' мин' : '—';
            document.querySelector('[data-analytics="popular_service"]').textContent = a.popular_service;
        }

        function getFiltered() {
            const q = document.getElementById('services-search').value.trim().toLowerCase();
            const status = document.getElementById('filter-status').value;
            const sort = document.getElementById('sort-by').value;
            let items = (catalog.services || []).slice();

            if (q) {
                items = items.filter((s) => {
                    return (s.name || '').toLowerCase().includes(q) ||
                        (s.description || '').toLowerCase().includes(q);
                });
            }
            if (status === 'active') {
                items = items.filter((s) => s.is_active);
            } else if (status === 'inactive') {
                items = items.filter((s) => !s.is_active);
            }

            const sorters = {
                name: (a, b) => a.name.localeCompare(b.name, 'ru'),
                price: (a, b) => (b.price || 0) - (a.price || 0),
                duration: (a, b) => b.duration_minutes - a.duration_minutes,
                created: (a, b) => (b.created_at || '').localeCompare(a.created_at || ''),
                updated: (a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''),
                manual: (a, b) => a.sort_order - b.sort_order,
            };
            items.sort(sorters[sort] || sorters.name);
            return items;
        }

        function filterAndRender() {
            filtered = getFiltered();
            render();
        }

        function render() {
            loading.hidden = true;
            closeMenus();

            if (!catalog.services.length) {
                grid.hidden = true;
                empty.hidden = false;
                pagination.hidden = true;
                return;
            }

            if (!filtered.length) {
                grid.hidden = true;
                empty.hidden = false;
                empty.querySelector('.services-empty__title').textContent = 'Ничего не найдено';
                empty.querySelector('.services-empty__text').textContent = 'Измените поиск или фильтры';
                pagination.hidden = true;
                return;
            }

            empty.hidden = true;
            grid.hidden = false;

            const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
            if (currentPage > totalPages) currentPage = totalPages;
            const start = (currentPage - 1) * PAGE_SIZE;
            const pageItems = filtered.slice(start, start + PAGE_SIZE);

            grid.innerHTML = '';
            pageItems.forEach((service) => {
                grid.appendChild(createCard(service));
            });

            renderPagination(totalPages);
            updateBulkBar();
        }

        function createCard(service) {
            const card = document.createElement('article');
            card.className = 'service-card';
            card.style.setProperty('--service-color', service.color);
            card.dataset.id = service.id;
            if (selectedIds.has(service.id)) {
                card.classList.add('is-selected');
            }

            const sortManual = document.getElementById('sort-by').value === 'manual';
            if (sortManual) {
                card.draggable = true;
                card.addEventListener('dragstart', (e) => {
                    e.dataTransfer.setData('text/plain', String(service.id));
                    card.classList.add('is-dragging');
                });
                card.addEventListener('dragend', () => card.classList.remove('is-dragging'));
                card.addEventListener('dragover', (e) => e.preventDefault());
                card.addEventListener('drop', async (e) => {
                    e.preventDefault();
                    const fromId = parseInt(e.dataTransfer.getData('text/plain'), 10);
                    const toId = service.id;
                    if (fromId === toId) return;
                    await reorderCards(fromId, toId);
                });
            }

            card.innerHTML =
                '<label class="service-card__select">' +
                    '<input type="checkbox" data-select="' + service.id + '"' + (selectedIds.has(service.id) ? ' checked' : '') + '>' +
                '</label>' +
                '<div class="service-card__head">' +
                    '<div class="service-card__icon" aria-hidden="true">' + service.icon_display + '</div>' +
                    '<div class="service-card__info">' +
                        '<h3 class="service-card__title">' + escapeHtml(service.name) + '</h3>' +
                        '<p class="service-card__desc">' + escapeHtml(service.description || 'Без описания') + '</p>' +
                    '</div>' +
                    '<span class="service-card__status badge ' + (service.is_active ? 'badge--success' : 'badge--ghost') + '">' +
                        (service.is_active ? 'Активна' : 'Отключена') +
                    '</span>' +
                    '<div class="service-card__menu-wrap">' +
                        '<button type="button" class="service-card__menu-btn" data-menu="' + service.id + '" aria-label="Меню">⋮</button>' +
                        '<div class="service-card__menu" hidden>' +
                            '<button type="button" data-action="edit" data-id="' + service.id + '">Редактировать</button>' +
                            '<button type="button" data-action="duplicate" data-id="' + service.id + '">Дублировать</button>' +
                            '<button type="button" data-action="stats" data-id="' + service.id + '">Статистика</button>' +
                            '<button type="button" data-action="toggle" data-id="' + service.id + '">' +
                                (service.is_active ? 'Отключить' : 'Включить') +
                            '</button>' +
                            '<button type="button" class="is-danger" data-action="delete" data-id="' + service.id + '">Удалить</button>' +
                        '</div>' +
                    '</div>' +
                '</div>' +
                '<div class="service-card__badges">' +
                    '<span class="service-card__badge">⏱ ' + service.duration_minutes + ' мин</span>' +
                    '<span class="service-card__badge">💳 ' + (service.price != null ? Math.round(service.price) + ' ₽' : '—') + '</span>' +
                    '<span class="service-card__badge">📅 ' + escapeHtml(service.calendar_name || '—') + '</span>' +
                '</div>';

            card.querySelector('[data-select]').addEventListener('change', (e) => {
                e.stopPropagation();
                if (e.target.checked) {
                    selectedIds.add(service.id);
                } else {
                    selectedIds.delete(service.id);
                }
                card.classList.toggle('is-selected', e.target.checked);
                updateBulkBar();
            });

            card.querySelector('[data-menu]').addEventListener('click', (e) => {
                e.stopPropagation();
                toggleMenu(service.id, card.querySelector('.service-card__menu'));
            });

            card.querySelectorAll('.service-card__menu button').forEach((btn) => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    closeMenus();
                    handleAction(btn.dataset.action, service.id);
                });
            });

            card.addEventListener('click', (e) => {
                if (e.target.closest('.service-card__menu-wrap') || e.target.closest('.service-card__select')) {
                    return;
                }
                const svc = catalog.services.find((s) => s.id === service.id);
                if (svc) drawer.openEdit(svc, catalog.calendars);
            });

            return card;
        }

        async function handleAction(action, id) {
            const service = catalog.services.find((s) => s.id === id);
            if (!service) return;
            try {
                if (action === 'edit') {
                    drawer.openEdit(service, catalog.calendars);
                } else if (action === 'duplicate') {
                    const data = await api.duplicateService(id);
                    showToast(data.message);
                    applyCatalog(data.catalog);
                } else if (action === 'stats') {
                    drawer.openEdit(service, catalog.calendars);
                } else if (action === 'toggle') {
                    const data = await api.updateService(id, { is_active: !service.is_active });
                    showToast(service.is_active ? 'Услуга отключена' : 'Услуга включена');
                    applyCatalog(data.catalog);
                } else if (action === 'delete') {
                    if (!window.confirm('Удалить услугу?')) return;
                    const data = await api.deleteService(id);
                    showToast(data.message);
                    selectedIds.delete(id);
                    applyCatalog(data.catalog);
                }
            } catch (error) {
                showToast(error.message, 'error');
            }
        }

        function toggleMenu(id, menuEl) {
            if (openMenuId === id) {
                closeMenus();
                return;
            }
            closeMenus();
            openMenuId = id;
            menuEl.hidden = false;
        }

        function closeMenus() {
            openMenuId = null;
            document.querySelectorAll('.service-card__menu').forEach((m) => { m.hidden = true; });
        }

        function renderPagination(totalPages) {
            if (totalPages <= 1) {
                pagination.hidden = true;
                return;
            }
            pagination.hidden = false;
            pagination.innerHTML = '';
            for (let i = 1; i <= totalPages; i++) {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.textContent = String(i);
                btn.classList.toggle('is-active', i === currentPage);
                btn.addEventListener('click', () => {
                    currentPage = i;
                    render();
                    grid.scrollIntoView({ behavior: 'smooth', block: 'start' });
                });
                pagination.appendChild(btn);
            }
        }

        function updateBulkBar() {
            const count = selectedIds.size;
            bulkBar.hidden = count === 0;
            document.getElementById('bulk-count').textContent = count + ' выбрано';
        }

        async function bulkAction(action) {
            if (!selectedIds.size) return;
            if (action === 'delete' && !window.confirm('Удалить выбранные услуги?')) return;
            try {
                const data = await api.bulkAction({
                    service_ids: Array.from(selectedIds),
                    action: action === 'activate' ? 'activate' : action === 'deactivate' ? 'deactivate' : 'delete',
                });
                showToast(data.message);
                selectedIds.clear();
                applyCatalog(data.catalog);
            } catch (error) {
                showToast(error.message, 'error');
            }
        }

        async function reorderCards(fromId, toId) {
            const ids = catalog.services
                .slice()
                .sort((a, b) => a.sort_order - b.sort_order)
                .map((s) => s.id);
            const fromIdx = ids.indexOf(fromId);
            const toIdx = ids.indexOf(toId);
            if (fromIdx < 0 || toIdx < 0) return;
            ids.splice(fromIdx, 1);
            ids.splice(toIdx, 0, fromId);
            try {
                const data = await api.reorder(ids);
                document.getElementById('sort-by').value = 'manual';
                applyCatalog(data.catalog);
                showToast(data.message);
            } catch (error) {
                showToast(error.message, 'error');
            }
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        load();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
