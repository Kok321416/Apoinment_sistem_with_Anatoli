(function (global) {
    const GRID_HEIGHT = 720;
    const MINUTES_PER_DAY = 24 * 60;
    const SNAP = 15;

    function timeOptions(select) {
        select.innerHTML = '<option value="">Выберите</option>';
        for (let hour = 0; hour < 24; hour++) {
            for (let minute = 0; minute < 60; minute += 30) {
                const value = String(hour).padStart(2, '0') + ':' + String(minute).padStart(2, '0');
                const option = document.createElement('option');
                option.value = value;
                option.textContent = value;
                select.appendChild(option);
            }
        }
    }

    function minutesFromTime(value) {
        const parts = value.split(':');
        return parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10);
    }

    function timeFromMinutes(minutes) {
        minutes = Math.max(0, Math.min(MINUTES_PER_DAY - 1, minutes));
        const h = Math.floor(minutes / 60);
        const m = minutes % 60;
        return String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0');
    }

    function snap(minutes) {
        return Math.round(minutes / SNAP) * SNAP;
    }

    class CalendarWeekGrid {
        constructor(container, options) {
            this.container = container;
            this.onDaySelect = options.onDaySelect;
            this.onSlotUpdate = options.onSlotUpdate;
            this.onSlotSelect = options.onSlotSelect;
            this.onSlotDelete = options.onSlotDelete;
            this.selectedDay = options.selectedDay || 0;
            this.schedule = null;
            this._drag = null;
        }

        render(schedule) {
            this.schedule = schedule;
            this.container.innerHTML = '';
            this.container.hidden = false;

            const scale = document.createElement('div');
            scale.className = 'week-grid__scale';
            for (let hour = 0; hour <= 24; hour++) {
                const label = document.createElement('div');
                label.className = 'week-grid__hour';
                label.style.top = (hour / 24 * 100) + '%';
                label.textContent = String(hour).padStart(2, '0') + ':00';
                scale.appendChild(label);
            }
            this.container.appendChild(scale);

            for (let hour = 0; hour <= 24; hour++) {
                const line = document.createElement('div');
                line.className = 'week-grid__hour-line';
                line.style.top = (hour / 24 * 100) + '%';
                this.container.appendChild(line);
            }

            schedule.week.forEach((day) => {
                const column = document.createElement('div');
                column.className = 'week-grid__column';
                column.dataset.day = String(day.day);
                if (day.day === this.selectedDay) {
                    column.classList.add('is-selected');
                }
                if (!day.is_working) {
                    column.classList.add('is-off');
                }

                const head = document.createElement('div');
                head.className = 'week-grid__column-head';
                head.textContent = day.short;
                column.appendChild(head);

                const body = document.createElement('div');
                body.className = 'week-grid__column-body';
                day.slots.forEach((slot) => {
                    body.appendChild(this._createSlotElement(day.day, slot));
                });
                column.appendChild(body);

                column.addEventListener('click', (event) => {
                    if (event.target.closest('.week-slot')) {
                        return;
                    }
                    this.selectDay(day.day);
                });

                this.container.appendChild(column);
            });
        }

        selectDay(day) {
            this.selectedDay = day;
            this.container.querySelectorAll('.week-grid__column').forEach((col) => {
                col.classList.toggle('is-selected', parseInt(col.dataset.day, 10) === day);
            });
            if (this.onDaySelect) {
                this.onDaySelect(day);
            }
        }

        _createSlotElement(day, slot) {
            const el = document.createElement('div');
            el.className = 'week-slot';
            el.dataset.id = String(slot.id);
            el.dataset.day = String(day);
            el.style.top = slot.top + '%';
            el.style.height = slot.height + '%';
            el.title = slot.start + ' – ' + slot.end + ' · клик: изменить';
            el.innerHTML =
                '<span class="week-slot__resize week-slot__resize--top" data-edge="top"></span>' +
                '<span class="week-slot__label">' + slot.start + '<br>' + slot.end + '</span>' +
                '<button type="button" class="week-slot__delete" data-slot-id="' + slot.id + '" title="Удалить окно" aria-label="Удалить окно ' + slot.start + '–' + slot.end + '">×</button>' +
                '<span class="week-slot__resize week-slot__resize--bottom" data-edge="bottom"></span>';

            el.addEventListener('click', (event) => {
                if (event.target.closest('.week-slot__delete') || event.target.closest('.week-slot__resize')) {
                    return;
                }
                event.stopPropagation();
                this.selectDay(day);
                if (this.onSlotSelect) {
                    this.onSlotSelect(day, slot);
                }
            });

            const deleteBtn = el.querySelector('.week-slot__delete');
            if (deleteBtn) {
                deleteBtn.addEventListener('click', (event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    if (this.onSlotDelete) {
                        this.onSlotDelete(slot.id, day);
                    }
                });
            }

            el.querySelectorAll('.week-slot__resize').forEach((handle) => {
                handle.addEventListener('pointerdown', (event) => this._startResize(event, slot, handle.dataset.edge));
            });

            return el;
        }

        _startResize(event, slot, edge) {
            event.preventDefault();
            event.stopPropagation();
            const columnBody = event.target.closest('.week-grid__column-body');
            if (!columnBody) {
                return;
            }
            const rect = columnBody.getBoundingClientRect();
            const startY = event.clientY;
            const startMinutes = minutesFromTime(slot.start);
            const endMinutes = minutesFromTime(slot.end);
            const slotEl = event.target.closest('.week-slot');
            slotEl.classList.add('is-dragging');

            const onMove = (moveEvent) => {
                const deltaPx = moveEvent.clientY - startY;
                const deltaMinutes = snap((deltaPx / rect.height) * MINUTES_PER_DAY);
                let newStart = startMinutes;
                let newEnd = endMinutes;
                if (edge === 'top') {
                    newStart = snap(startMinutes + deltaMinutes);
                    newStart = Math.min(newStart, newEnd - SNAP);
                } else {
                    newEnd = snap(endMinutes + deltaMinutes);
                    newEnd = Math.max(newEnd, newStart + SNAP);
                }
                if (newEnd <= newStart) {
                    return;
                }
                slotEl.style.top = (newStart / MINUTES_PER_DAY * 100) + '%';
                slotEl.style.height = ((newEnd - newStart) / MINUTES_PER_DAY * 100) + '%';
                slotEl.querySelector('.week-slot__label').innerHTML =
                    timeFromMinutes(newStart) + '<br>' + timeFromMinutes(newEnd);
                slotEl.dataset.pendingStart = timeFromMinutes(newStart);
                slotEl.dataset.pendingEnd = timeFromMinutes(newEnd);
            };

            const onUp = async () => {
                document.removeEventListener('pointermove', onMove);
                document.removeEventListener('pointerup', onUp);
                slotEl.classList.remove('is-dragging');
                const newStart = slotEl.dataset.pendingStart;
                const newEnd = slotEl.dataset.pendingEnd;
                delete slotEl.dataset.pendingStart;
                delete slotEl.dataset.pendingEnd;
                if (!newStart || !newEnd || (newStart === slot.start && newEnd === slot.end)) {
                    return;
                }
                if (this.onSlotUpdate) {
                    await this.onSlotUpdate(slot.id, newStart, newEnd);
                }
            };

            document.addEventListener('pointermove', onMove);
            document.addEventListener('pointerup', onUp);
        }
    }

    global.CalendarWeekGrid = CalendarWeekGrid;
    global.calendarTimeOptions = timeOptions;
})(window);
