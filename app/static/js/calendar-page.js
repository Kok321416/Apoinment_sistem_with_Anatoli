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

        let selectedDay = new Date().getDay();
        selectedDay = selectedDay === 0 ? 6 : selectedDay - 1;

        let lastSchedule = null;

        function getSchedule() {
            return lastSchedule;
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

        let weekGrid = null;
        let dayEditor = null;

        async function applySchedule(schedule, dayData) {
            lastSchedule = schedule;
            renderBadges(schedule.settings);
            syncSettingsForm(schedule.settings);
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

                gridLoading.hidden = true;
                editorLoading.hidden = true;

                weekGrid = new CalendarWeekGrid(gridEl, {
                    selectedDay: selectedDay,
                    onDaySelect: (day) => {
                        selectedDay = day;
                        weekGrid.selectedDay = day;
                        if (!lastSchedule || !lastSchedule.week) {
                            return;
                        }
                        dayEditor.renderDay(lastSchedule.week[day]);
                    },
                    onSlotSelect: (day, slot) => {
                        selectedDay = day;
                        weekGrid.selectedDay = day;
                        if (!lastSchedule || !lastSchedule.week) {
                            return;
                        }
                        dayEditor.renderDay(lastSchedule.week[day]);
                        dayEditor.editSlot(slot.id);
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
