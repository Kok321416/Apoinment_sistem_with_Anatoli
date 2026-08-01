(function () {
    function init() {
        const page = document.getElementById('calendar-page');
        if (!page) {
            return;
        }

        const calendarId = parseInt(page.dataset.calendarId, 10);
        const csrfToken = page.dataset.csrf || '';
        const api = new CalendarApi(calendarId, csrfToken);

        const gridEl = document.getElementById('week-grid');
        const gridLoading = document.getElementById('week-grid-loading');
        const editorEl = document.getElementById('day-editor');
        const editorLoading = document.getElementById('day-editor-loading');
        const badgesEl = document.getElementById('calendar-badges');
        const settingsForm = document.getElementById('calendar-settings-form');
        const copyBtn = document.getElementById('copy-booking-link');
        const dayChipsEl = document.getElementById('schedule-day-chips');
        const mobileProgress = document.getElementById('schedule-mobile-progress');
        const settingsPanel = document.getElementById('calendar-settings-panel');
        const settingsToggle = document.getElementById('calendar-settings-toggle');

        let selectedDay = new Date().getDay();
        selectedDay = selectedDay === 0 ? 6 : selectedDay - 1;

        let lastSchedule = null;

        function getSchedule() {
            return lastSchedule;
        }

        function isMobileSchedule() {
            return window.matchMedia('(max-width: 768px)').matches;
        }

        function renderBadges(settings) {
            const limit = settings.max_services_per_day
                ? settings.max_services_per_day
                : '—';
            const reminders = [];
            if (settings.reminder_hours_first) {
                reminders.push('за ' + settings.reminder_hours_first + ' ч');
            }
            if (settings.reminder_hours_second) {
                reminders.push('за ' + settings.reminder_hours_second + ' ч');
            }
            badgesEl.innerHTML =
                '<span class="calendar-badge"><strong>Перерыв:</strong> ' + settings.break_between_services_minutes + ' мин</span>' +
                '<span class="calendar-badge"><strong>Лимит в день:</strong> ' + limit + '</span>' +
                '<span class="calendar-badge"><strong>Запись за:</strong> ' + settings.book_ahead_hours + ' ч</span>' +
                '<span class="calendar-badge"><strong>Напоминания:</strong> ' + (reminders.length ? reminders.join(' и ') : 'выкл') + '</span>';
        }

        function syncSettingsForm(settings) {
            document.getElementById('setting-break').value = settings.break_between_services_minutes;
            document.getElementById('setting-limit').value = settings.max_services_per_day;
            document.getElementById('setting-ahead').value = settings.book_ahead_hours;
            document.getElementById('setting-reminder-first').value = settings.reminder_hours_first || 6;
            document.getElementById('setting-reminder-second').value = settings.reminder_hours_second || 1;
            document.getElementById('setting-reminder-first-enabled').checked = settings.reminder_hours_first > 0;
            document.getElementById('setting-reminder-second-enabled').checked = settings.reminder_hours_second > 0;
        }

        function renderDayChips(schedule) {
            if (!dayChipsEl || !schedule || !schedule.week) {
                return;
            }
            dayChipsEl.innerHTML = '';
            schedule.week.forEach(function (day) {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'schedule-day-chip';
                btn.setAttribute('role', 'tab');
                btn.dataset.day = String(day.day);
                if (day.day === selectedDay) {
                    btn.classList.add('is-selected');
                    btn.setAttribute('aria-selected', 'true');
                } else {
                    btn.setAttribute('aria-selected', 'false');
                }
                if (!day.is_working) {
                    btn.classList.add('is-off');
                }
                const slotCount = (day.slots && day.slots.length) || 0;
                btn.innerHTML =
                    '<span class="schedule-day-chip__short">' + (day.short || '') + '</span>' +
                    '<span class="schedule-day-chip__meta">' +
                    (day.is_working ? slotCount + ' окн.' : 'вых.') +
                    '</span>';
                btn.addEventListener('click', function () {
                    selectDay(day.day, { scrollEditor: true });
                });
                dayChipsEl.appendChild(btn);
            });
        }

        function syncDayChipSelection() {
            if (!dayChipsEl) return;
            dayChipsEl.querySelectorAll('.schedule-day-chip').forEach(function (chip) {
                const day = parseInt(chip.dataset.day, 10);
                const on = day === selectedDay;
                chip.classList.toggle('is-selected', on);
                chip.setAttribute('aria-selected', on ? 'true' : 'false');
            });
        }

        function selectDay(day, opts) {
            selectedDay = day;
            if (weekGrid) {
                weekGrid.selectDay(day);
            } else if (lastSchedule && lastSchedule.week && dayEditor) {
                dayEditor.renderDay(lastSchedule.week[day]);
            }
            syncDayChipSelection();
            if (opts && opts.scrollEditor && isMobileSchedule()) {
                const panel = document.getElementById('day-editor-panel');
                if (panel) {
                    panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            }
        }

        function wireMobileProgress() {
            if (!mobileProgress) return;
            mobileProgress.hidden = false;
            const links = Array.prototype.slice.call(
                mobileProgress.querySelectorAll('.schedule-mobile-progress__item')
            );
            const sections = {
                day: document.getElementById('day-editor-panel'),
                settings: document.getElementById('calendar-settings-panel'),
                summary: document.getElementById('calendar-settings-summary'),
            };

            links.forEach(function (link) {
                link.addEventListener('click', function (e) {
                    const key = link.getAttribute('data-section');
                    const target = sections[key];
                    if (!target) return;
                    e.preventDefault();
                    if (key === 'settings' && settingsPanel && !settingsPanel.classList.contains('is-open')) {
                        settingsPanel.classList.add('is-open');
                        if (settingsToggle) settingsToggle.setAttribute('aria-expanded', 'true');
                    }
                    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                });
            });

            if (!('IntersectionObserver' in window)) return;
            const observer = new IntersectionObserver(
                function (entries) {
                    entries.forEach(function (entry) {
                        if (!entry.isIntersecting) return;
                        const id = entry.target.id;
                        let key = 'day';
                        if (id === 'calendar-settings-panel') key = 'settings';
                        if (id === 'calendar-settings-summary') key = 'summary';
                        links.forEach(function (link) {
                            link.classList.toggle(
                                'is-active',
                                link.getAttribute('data-section') === key
                            );
                        });
                    });
                },
                { root: null, rootMargin: '-35% 0px -50% 0px', threshold: 0.01 }
            );
            Object.keys(sections).forEach(function (k) {
                if (sections[k]) observer.observe(sections[k]);
            });
        }

        if (settingsToggle && settingsPanel) {
            settingsToggle.addEventListener('click', function () {
                if (!isMobileSchedule()) return;
                const open = !settingsPanel.classList.contains('is-open');
                settingsPanel.classList.toggle('is-open', open);
                settingsToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
            });
        }

        let weekGrid = null;
        let dayEditor = null;

        async function applySchedule(schedule, dayData) {
            lastSchedule = schedule;
            renderBadges(schedule.settings);
            syncSettingsForm(schedule.settings);
            renderDayChips(schedule);
            if (weekGrid) {
                weekGrid.selectedDay = selectedDay;
                weekGrid.render(schedule);
            }
            const day = dayData || (schedule.week && schedule.week[selectedDay]);
            if (day && dayEditor) {
                editorLoading.hidden = true;
                dayEditor.renderDay(day);
            }
        }

        async function onScheduleChange(schedule, dayData) {
            await applySchedule(schedule, dayData);
        }

        async function loadSchedule() {
            page.classList.add('is-loading');
            try {
                const schedule = await api.getSchedule();
                lastSchedule = schedule;
                renderBadges(schedule.settings);
                syncSettingsForm(schedule.settings);
                renderDayChips(schedule);

                gridLoading.hidden = true;
                editorLoading.hidden = true;

                weekGrid = new CalendarWeekGrid(gridEl, {
                    selectedDay: selectedDay,
                    onDaySelect: (day) => {
                        selectedDay = day;
                        weekGrid.selectedDay = day;
                        syncDayChipSelection();
                        if (!lastSchedule || !lastSchedule.week) {
                            return;
                        }
                        dayEditor.renderDay(lastSchedule.week[day]);
                    },
                    onSlotSelect: (day, slot) => {
                        selectedDay = day;
                        weekGrid.selectedDay = day;
                        syncDayChipSelection();
                        if (!lastSchedule || !lastSchedule.week) {
                            return;
                        }
                        dayEditor.renderDay(lastSchedule.week[day]);
                        dayEditor.editSlot(slot.id);
                        if (isMobileSchedule()) {
                            const panel = document.getElementById('day-editor-panel');
                            if (panel) {
                                panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
                            }
                        }
                    },
                    onSlotDelete: async (slotId, day) => {
                        if (!window.confirm('Удалить это окно?')) {
                            return;
                        }
                        try {
                            selectedDay = day;
                            const data = await api.deleteSlot(slotId);
                            showToast(data.message || 'Окно удалено');
                            await applySchedule(data.schedule, data.schedule.week[day]);
                        } catch (error) {
                            showToast(error.message, 'error');
                        }
                    },
                    onSlotUpdate: async (slotId, start, end) => {
                        try {
                            const data = await api.updateSlot(slotId, { start_time: start, end_time: end });
                            showToast(data.message || 'Окно обновлено');
                            await applySchedule(data.schedule, data.schedule.week[selectedDay]);
                        } catch (error) {
                            showToast(error.message, 'error');
                            weekGrid.render(lastSchedule);
                        }
                    },
                });
                weekGrid.render(schedule);

                dayEditor = new CalendarDayEditor(editorEl, {
                    api: api,
                    daysNames: schedule.days_names,
                    getSchedule: getSchedule,
                    onScheduleChange: onScheduleChange,
                });
                dayEditor.renderDay(schedule.week[selectedDay]);
                wireMobileProgress();
            } catch (error) {
                gridLoading.textContent = 'Не удалось загрузить расписание: ' + error.message;
                showToast(error.message, 'error');
            } finally {
                page.classList.remove('is-loading');
            }
        }

        if (copyBtn && typeof copyBookingLink === 'function') {
            copyBtn.addEventListener('click', function () {
                copyBookingLink(copyBtn);
            });
        }

        settingsForm.addEventListener('submit', async (event) => {
            event.preventDefault();
            const btn = document.getElementById('settings-save-btn');
            btn.disabled = true;
            try {
                const payload = {
                    break_between_services_minutes: parseInt(document.getElementById('setting-break').value, 10) || 0,
                    max_services_per_day: parseInt(document.getElementById('setting-limit').value, 10) || 0,
                    book_ahead_hours: parseInt(document.getElementById('setting-ahead').value, 10) || 0,
                    reminder_hours_first: parseInt(document.getElementById('setting-reminder-first').value, 10) || 6,
                    reminder_hours_second: parseInt(document.getElementById('setting-reminder-second').value, 10) || 1,
                    reminder_first_enabled: document.getElementById('setting-reminder-first-enabled').checked,
                    reminder_second_enabled: document.getElementById('setting-reminder-second-enabled').checked,
                };
                const data = await api.saveSettings(payload);
                showToast(data.message || 'Настройки сохранены');
                if (lastSchedule) {
                    lastSchedule.settings = data.settings;
                    lastSchedule.calendar = data.settings;
                    renderBadges(data.settings);
                }
            } catch (error) {
                showToast(error.message, 'error');
            } finally {
                btn.disabled = false;
            }
        });

        loadSchedule();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
