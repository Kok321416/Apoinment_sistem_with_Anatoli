(function (global) {
    class CalendarDayEditor {
        constructor(container, options) {
            this.container = container;
            this.api = options.api;
            this.daysNames = options.daysNames || [];
            this.getSchedule = options.getSchedule || (() => null);
            this.onScheduleChange = options.onScheduleChange;
            this.selectedDay = 0;
            this.dayData = null;
            this._editingSlotId = null;
        }

        renderDay(dayData) {
            if (this.selectedDay !== dayData.day) {
                this._editingSlotId = null;
            }
            this.dayData = dayData;
            this.selectedDay = dayData.day;
            this.container.hidden = false;
            this._render();
        }

        _render() {
            this.container.innerHTML = this._template(this.dayData);
            this._bindEvents();
            if (this._editingSlotId) {
                const slot = this.dayData.slots.find((s) => s.id === this._editingSlotId);
                const startSelect = this.container.querySelector('.edit-start');
                const endSelect = this.container.querySelector('.edit-end');
                if (slot && startSelect && endSelect) {
                    global.calendarTimeOptions(startSelect);
                    global.calendarTimeOptions(endSelect);
                    startSelect.value = slot.start;
                    endSelect.value = slot.end;
                }
            }
        }

        _template(dayData) {
            const slotsHtml = dayData.slots.length
                ? dayData.slots.map((slot) => this._slotCard(slot)).join('')
                : '<p class="day-editor__empty">Нет временных окон</p>';

            return (
                '<div class="day-editor">' +
                    '<div class="day-editor__head">' +
                        '<h2 class="day-editor__title">' + this._escape(dayData.name) + '</h2>' +
                        '<label class="day-editor__toggle">' +
                            '<span>Рабочий день</span>' +
                            '<span class="toggle-switch">' +
                                '<input type="checkbox" id="day-working-toggle"' + (dayData.is_working ? ' checked' : '') + '>' +
                                '<span class="toggle-switch__track"></span>' +
                            '</span>' +
                        '</label>' +
                    '</div>' +
                    '<div class="day-editor__slots" id="day-slots-list">' + slotsHtml + '</div>' +
                    '<div class="day-editor__add">' +
                        '<p class="settings-card__label">Добавить окно</p>' +
                        '<div class="day-editor__add-row">' +
                            '<div class="form-field">' +
                                '<label class="form-field__label" for="add-start">С</label>' +
                                '<select class="select" id="add-start"></select>' +
                            '</div>' +
                            '<div class="form-field">' +
                                '<label class="form-field__label" for="add-end">До</label>' +
                                '<select class="select" id="add-end"></select>' +
                            '</div>' +
                            '<button type="button" class="btn btn--primary btn--sm" id="add-slot-btn">Добавить</button>' +
                        '</div>' +
                    '</div>' +
                    '<div class="quick-actions">' +
                        '<button type="button" class="quick-action" data-action="copy">' +
                            '<span class="quick-action__title">Копировать расписание</span>' +
                            '<span class="quick-action__desc">На другие дни недели</span>' +
                        '</button>' +
                        '<button type="button" class="quick-action" data-action="workweek">' +
                            '<span class="quick-action__title">Рабочая неделя</span>' +
                            '<span class="quick-action__desc">Пн–Пт как этот день</span>' +
                        '</button>' +
                        '<button type="button" class="quick-action" data-action="fulltime">' +
                            '<span class="quick-action__title">24/7</span>' +
                            '<span class="quick-action__desc">Окно 00:00–23:59</span>' +
                        '</button>' +
                        '<button type="button" class="quick-action" data-action="clear">' +
                            '<span class="quick-action__title">Очистить день</span>' +
                            '<span class="quick-action__desc">Удалить все окна</span>' +
                        '</button>' +
                        '<button type="button" class="quick-action" data-action="weekend">' +
                            '<span class="quick-action__title">Сделать выходным</span>' +
                            '<span class="quick-action__desc">Отключить день полностью</span>' +
                        '</button>' +
                    '</div>' +
                '</div>'
            );
        }

        _slotCard(slot) {
            const editing = this._editingSlotId === slot.id;
            if (editing) {
                return (
                    '<div class="slot-card" data-slot-id="' + slot.id + '">' +
                        '<div class="day-editor__add-row">' +
                            '<div class="form-field">' +
                                '<select class="select edit-start" data-slot-id="' + slot.id + '"></select>' +
                            '</div>' +
                            '<div class="form-field">' +
                                '<select class="select edit-end" data-slot-id="' + slot.id + '"></select>' +
                            '</div>' +
                            '<button type="button" class="btn btn--primary btn--sm save-edit-btn" data-slot-id="' + slot.id + '">Сохранить</button>' +
                            '<button type="button" class="btn btn--ghost btn--sm cancel-edit-btn" data-slot-id="' + slot.id + '">Отмена</button>' +
                        '</div>' +
                    '</div>'
                );
            }
            return (
                '<div class="slot-card' + (editing ? ' slot-card--editing' : '') + '" data-slot-id="' + slot.id + '">' +
                    '<span class="slot-card__time">' + slot.start + ' — ' + slot.end + '</span>' +
                    '<div class="slot-card__actions">' +
                        '<button type="button" class="slot-card__action edit-slot-btn" data-slot-id="' + slot.id + '">' +
                            '<span class="slot-card__action-icon" aria-hidden="true">✏</span>' +
                            '<span class="slot-card__action-label">Изменить</span>' +
                        '</button>' +
                        '<button type="button" class="slot-card__action slot-card__action--danger delete-slot-btn" data-slot-id="' + slot.id + '">' +
                            '<span class="slot-card__action-icon" aria-hidden="true">🗑</span>' +
                            '<span class="slot-card__action-label">Удалить</span>' +
                        '</button>' +
                    '</div>' +
                '</div>'
            );
        }

        _bindEvents() {
            global.calendarTimeOptions(document.getElementById('add-start'));
            global.calendarTimeOptions(document.getElementById('add-end'));

            document.getElementById('day-working-toggle').addEventListener('change', async (event) => {
                await this._setWorking(event.target.checked);
            });

            document.getElementById('add-slot-btn').addEventListener('click', () => this._addSlot());

            this.container.querySelectorAll('.edit-slot-btn').forEach((btn) => {
                btn.addEventListener('click', () => {
                    this._editingSlotId = parseInt(btn.dataset.slotId, 10);
                    this._render();
                });
            });

            this.container.querySelectorAll('.cancel-edit-btn').forEach((btn) => {
                btn.addEventListener('click', () => {
                    this._editingSlotId = null;
                    this._render();
                });
            });

            this.container.querySelectorAll('.save-edit-btn').forEach((btn) => {
                btn.addEventListener('click', () => this._saveEdit(parseInt(btn.dataset.slotId, 10)));
            });

            this.container.querySelectorAll('.delete-slot-btn').forEach((btn) => {
                btn.addEventListener('click', () => this._deleteSlot(parseInt(btn.dataset.slotId, 10)));
            });

            this.container.querySelectorAll('[data-action]').forEach((btn) => {
                btn.addEventListener('click', () => this._quickAction(btn.dataset.action));
            });
        }

        async _addSlot() {
            const start = document.getElementById('add-start').value;
            const end = document.getElementById('add-end').value;
            if (!start || !end) {
                global.showToast('Выберите время начала и окончания', 'error');
                return;
            }
            try {
                const data = await this.api.createSlot({
                    day_of_week: this.selectedDay,
                    start_time: start,
                    end_time: end,
                });
                global.showToast(data.message || 'Окно добавлено');
                await this._applySchedule(data.schedule, data.schedule.week[this.selectedDay]);
            } catch (error) {
                global.showToast(error.message, 'error');
            }
        }

        async _saveEdit(slotId) {
            const start = this.container.querySelector('.edit-start').value;
            const end = this.container.querySelector('.edit-end').value;
            try {
                const data = await this.api.updateSlot(slotId, { start_time: start, end_time: end });
                this._editingSlotId = null;
                global.showToast(data.message || 'Окно обновлено');
                await this._applySchedule(data.schedule, data.schedule.week[this.selectedDay]);
            } catch (error) {
                global.showToast(error.message, 'error');
            }
        }

        async _deleteSlot(slotId) {
            if (!window.confirm('Удалить это окно?')) {
                return;
            }
            try {
                const data = await this.api.deleteSlot(slotId);
                global.showToast(data.message || 'Окно удалено');
                await this._applySchedule(data.schedule, data.schedule.week[this.selectedDay]);
            } catch (error) {
                global.showToast(error.message, 'error');
            }
        }

        async _setWorking(isWorking) {
            try {
                const data = await this.api.setDayWorking(this.selectedDay, isWorking);
                global.showToast(data.message);
                await this._applySchedule(data.schedule, data.day);
            } catch (error) {
                global.showToast(error.message, 'error');
            }
        }

        async _quickAction(action) {
            try {
                let data;
                if (action === 'copy') {
                    this._showCopyModal();
                    return;
                }
                if (action === 'workweek') {
                    if (!window.confirm('Заменить расписание Пн–Пт расписанием этого дня?')) {
                        return;
                    }
                    data = await this.api.presetWorkweek(this.selectedDay);
                } else if (action === 'fulltime') {
                    if (!window.confirm('Создать окно 00:00–23:59 для этого дня?')) {
                        return;
                    }
                    data = await this.api.presetFulltime([this.selectedDay]);
                } else if (action === 'clear') {
                    if (!window.confirm('Удалить все окна этого дня?')) {
                        return;
                    }
                    data = await this.api.clearDay(this.selectedDay);
                } else if (action === 'weekend') {
                    data = await this.api.setDayWorking(this.selectedDay, false);
                }
                if (data) {
                    global.showToast(data.message);
                    await this._applySchedule(data.schedule, data.schedule.week[this.selectedDay]);
                }
            } catch (error) {
                global.showToast(error.message, 'error');
            }
        }

        _showCopyModal() {
            const existing = document.getElementById('copy-days-modal');
            if (existing) {
                existing.remove();
            }
            const schedule = this.getSchedule();
            const week = schedule ? schedule.week : [];
            const modal = document.createElement('div');
            modal.id = 'copy-days-modal';
            modal.className = 'copy-days-modal';
            const checks = week.map((day) => {
                if (day.day === this.selectedDay) {
                    return '';
                }
                return (
                    '<label><input type="checkbox" value="' + day.day + '"> ' + day.name + '</label>'
                );
            }).join('');
            modal.innerHTML =
                '<div class="copy-days-modal__dialog">' +
                    '<h3 class="day-editor__title">Копировать на дни</h3>' +
                    '<p class="text-muted">Расписание дня «' + this._escape(this.dayData.name) + '» заменит выбранные дни.</p>' +
                    '<div class="copy-days-modal__days">' + checks + '</div>' +
                    '<div class="copy-days-modal__actions">' +
                        '<button type="button" class="btn btn--ghost btn--sm" id="copy-modal-cancel">Отмена</button>' +
                        '<button type="button" class="btn btn--primary btn--sm" id="copy-modal-ok">Копировать</button>' +
                    '</div>' +
                '</div>';
            document.body.appendChild(modal);
            modal.addEventListener('click', (event) => {
                if (event.target === modal) {
                    modal.remove();
                }
            });
            document.getElementById('copy-modal-cancel').addEventListener('click', () => modal.remove());
            document.getElementById('copy-modal-ok').addEventListener('click', async () => {
                const targetDays = Array.from(modal.querySelectorAll('input:checked')).map((el) => parseInt(el.value, 10));
                modal.remove();
                if (!targetDays.length) {
                    global.showToast('Выберите хотя бы один день', 'error');
                    return;
                }
                try {
                    const data = await this.api.copyDay(this.selectedDay, targetDays);
                    global.showToast(data.message || 'Расписание скопировано');
                    await this._applySchedule(data.schedule, data.schedule.week[this.selectedDay]);
                } catch (error) {
                    global.showToast(error.message, 'error');
                }
            });
        }

        async _applySchedule(schedule, dayData) {
            if (this.onScheduleChange) {
                await this.onScheduleChange(schedule, dayData);
            }
        }

        _escape(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
    }

    global.CalendarDayEditor = CalendarDayEditor;
})(window);
