(function (global) {
    const COLORS = ['#42c96b', '#f59e0b', '#7c5cff', '#ec4899', '#3b82f6', '#eab308', '#49d1ff', '#ff5c7a', '#3be4c8', '#667eea'];

    class ServiceDrawer {
        constructor(options) {
            this.api = options.api;
            this.onSaved = options.onSaved;
            this.backdrop = document.getElementById('drawer-backdrop');
            this.drawer = document.getElementById('service-drawer');
            this.titleEl = document.getElementById('drawer-title');
            this.form = document.getElementById('service-form');
            this.saveBtn = document.getElementById('drawer-save');
            this.deleteBtn = document.getElementById('drawer-delete');
            this.statsEl = document.getElementById('drawer-stats');
            this.templatesGrid = document.getElementById('templates-grid');
            this.calendars = [];
            this.templates = [];
            this.editingId = null;
            this._bind();
            this._renderColors();
        }

        _bind() {
            document.getElementById('drawer-close').addEventListener('click', () => this.close());
            this.backdrop.addEventListener('click', () => this.close());
            this.saveBtn.addEventListener('click', () => this.save());
            this.deleteBtn.addEventListener('click', () => this.remove());
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape' && this.drawer.classList.contains('is-open')) {
                    this.close();
                }
            });
        }

        _renderColors() {
            const palette = document.getElementById('color-palette');
            palette.innerHTML = '';
            COLORS.forEach((color) => {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'color-palette__swatch';
                btn.style.background = color;
                btn.dataset.color = color;
                btn.addEventListener('click', () => {
                    document.getElementById('service-color').value = color;
                    palette.querySelectorAll('.color-palette__swatch').forEach((el) => {
                        el.classList.toggle('is-selected', el.dataset.color === color);
                    });
                });
                palette.appendChild(btn);
            });
        }

        _selectColor(color) {
            document.getElementById('service-color').value = color || '#7d5cff';
            document.querySelectorAll('.color-palette__swatch').forEach((el) => {
                el.classList.toggle('is-selected', el.dataset.color === color);
            });
        }

        _fillCalendars(calendars, selectedId) {
            this.calendars = calendars;
            const select = document.getElementById('service-calendar');
            select.innerHTML = '';
            if (!calendars.length) {
                select.innerHTML = '<option value="">Сначала создайте календарь</option>';
                select.disabled = true;
                this.saveBtn.disabled = true;
                return;
            }
            select.disabled = false;
            this.saveBtn.disabled = false;
            calendars.forEach((cal) => {
                const opt = document.createElement('option');
                opt.value = cal.id;
                opt.textContent = cal.name;
                if (selectedId && cal.id === selectedId) {
                    opt.selected = true;
                }
                select.appendChild(opt);
            });
        }

        _renderTemplates() {
            this.templatesGrid.innerHTML = '';
            this.templates.forEach((tpl) => {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'template-chip';
                btn.textContent = tpl.name;
                btn.addEventListener('click', () => this.applyTemplate(tpl));
                this.templatesGrid.appendChild(btn);
            });
        }

        applyTemplate(tpl) {
            document.getElementById('service-name').value = tpl.name;
            document.getElementById('service-description').value = tpl.description || '';
            document.getElementById('service-duration').value = tpl.duration_minutes;
            document.getElementById('service-price').value = tpl.price || '';
            this._selectColor(tpl.color);
        }

        openCreate(calendars, templates) {
            this.editingId = null;
            this.templates = templates || [];
            this._renderTemplates();
            this.titleEl.textContent = 'Новая услуга';
            this.saveBtn.textContent = 'Создать';
            this.deleteBtn.hidden = true;
            this.statsEl.hidden = true;
            document.getElementById('service-id').value = '';
            document.getElementById('service-name').value = '';
            document.getElementById('service-description').value = '';
            document.getElementById('service-duration').value = 60;
            document.getElementById('service-price').value = '';
            document.getElementById('service-active').checked = true;
            this._selectColor('#7d5cff');
            this._fillCalendars(calendars);
            document.getElementById('drawer-templates').hidden = !this.templates.length;
            this._show();
        }

        async openEdit(service, calendars) {
            this.editingId = service.id;
            this.titleEl.textContent = 'Редактирование';
            this.saveBtn.textContent = 'Сохранить';
            this.deleteBtn.hidden = false;
            document.getElementById('drawer-templates').hidden = true;
            document.getElementById('service-id').value = service.id;
            document.getElementById('service-name').value = service.name;
            document.getElementById('service-description').value = service.description || '';
            document.getElementById('service-duration').value = service.duration_minutes;
            document.getElementById('service-price').value = service.price != null ? service.price : '';
            document.getElementById('service-active').checked = service.is_active;
            this._selectColor(service.color);
            this._fillCalendars(calendars, service.calendar_id);
            try {
                const data = await this.api.getStatistics(service.id);
                const st = data.statistics;
                this.statsEl.hidden = false;
                this.statsEl.innerHTML =
                    '<p><strong>Записей:</strong> ' + st.booking_count + '</p>' +
                    '<p><strong>Последняя запись:</strong> ' + (st.last_booking || '—') + '</p>' +
                    '<p><strong>Доход за запись:</strong> ' + st.avg_revenue + ' ₽</p>';
            } catch (e) {
                this.statsEl.hidden = true;
            }
            this._show();
        }

        openFromTemplate(tpl, calendars, templates) {
            this.openCreate(calendars, templates);
            this.applyTemplate(tpl);
        }

        _show() {
            this.backdrop.hidden = false;
            this.drawer.classList.add('is-open');
            this.drawer.setAttribute('aria-hidden', 'false');
            document.body.style.overflow = 'hidden';
        }

        close() {
            this.backdrop.hidden = true;
            this.drawer.classList.remove('is-open');
            this.drawer.setAttribute('aria-hidden', 'true');
            document.body.style.overflow = '';
        }

        async save() {
            const name = document.getElementById('service-name').value.trim();
            if (!name) {
                global.showToast('Укажите название услуги', 'error');
                return;
            }
            const calendarId = parseInt(document.getElementById('service-calendar').value, 10);
            if (!calendarId) {
                global.showToast('Выберите календарь', 'error');
                return;
            }
            const payload = {
                name: name,
                description: document.getElementById('service-description').value,
                duration_minutes: parseInt(document.getElementById('service-duration').value, 10) || 60,
                price: document.getElementById('service-price').value || null,
                calendar_id: calendarId,
                color: document.getElementById('service-color').value,
                is_active: document.getElementById('service-active').checked,
            };
            this.saveBtn.disabled = true;
            try {
                let data;
                if (this.editingId) {
                    data = await this.api.updateService(this.editingId, payload);
                    global.showToast(data.message || 'Услуга обновлена');
                } else {
                    data = await this.api.createService(payload);
                    global.showToast(data.message || 'Услуга создана');
                }
                this.close();
                if (this.onSaved) {
                    this.onSaved(data.catalog);
                }
            } catch (error) {
                global.showToast(error.message, 'error');
            } finally {
                this.saveBtn.disabled = false;
            }
        }

        async remove() {
            if (!this.editingId || !window.confirm('Удалить услугу?')) {
                return;
            }
            try {
                const data = await this.api.deleteService(this.editingId);
                global.showToast(data.message || 'Услуга удалена');
                this.close();
                if (this.onSaved) {
                    this.onSaved(data.catalog);
                }
            } catch (error) {
                global.showToast(error.message, 'error');
            }
        }
    }

    global.ServiceDrawer = ServiceDrawer;
})(window);
