(function (global) {
    class CalendarApi {
        constructor(calendarId, csrfToken) {
            this.calendarId = calendarId;
            this.csrfToken = csrfToken;
        }

        headers() {
            return {
                'Content-Type': 'application/json',
                'X-CSRF-Token': this.csrfToken,
            };
        }

        async request(url, options) {
            const response = await fetch(url, Object.assign({ credentials: 'same-origin' }, options || {}));
            let data = null;
            const raw = await response.text();
            if (raw) {
                try {
                    data = JSON.parse(raw);
                } catch (e) {
                    data = null;
                }
            }
            if (!response.ok) {
                let detail = data && (data.detail || data.error || data.message);
                if (Array.isArray(detail)) {
                    detail = detail.map(function (item) {
                        return typeof item === 'string' ? item : (item.msg || JSON.stringify(item));
                    }).join(', ');
                }
                if (!detail && response.status === 403) {
                    detail = 'Ошибка безопасности. Обновите страницу.';
                }
                if (!detail && response.status === 401) {
                    detail = 'Сессия истекла. Войдите снова.';
                }
                throw new Error(detail || ('Ошибка запроса (' + response.status + ')'));
            }
            return data;
        }

        getSchedule() {
            return this.request('/calendars/' + this.calendarId + '/schedule');
        }

        getDay(weekday) {
            return this.request('/calendars/' + this.calendarId + '/day/' + weekday);
        }

        createSlot(payload) {
            return this.request('/time-slots', {
                method: 'POST',
                headers: this.headers(),
                body: JSON.stringify(Object.assign({ calendar_id: this.calendarId, csrf_token: this.csrfToken }, payload)),
            });
        }

        updateSlot(slotId, payload) {
            return this.request('/time-slots/' + slotId, {
                method: 'PUT',
                headers: this.headers(),
                body: JSON.stringify(Object.assign({ csrf_token: this.csrfToken }, payload)),
            });
        }

        deleteSlot(slotId) {
            return this.request('/time-slots/' + slotId, {
                method: 'DELETE',
                headers: this.headers(),
            });
        }

        copyDay(sourceDay, targetDays) {
            return this.request('/calendars/' + this.calendarId + '/copy-day', {
                method: 'POST',
                headers: this.headers(),
                body: JSON.stringify({
                    source_day: sourceDay,
                    target_days: targetDays,
                    csrf_token: this.csrfToken,
                }),
            });
        }

        presetWorkweek(sourceDay) {
            return this.request('/calendars/' + this.calendarId + '/preset/workweek', {
                method: 'POST',
                headers: this.headers(),
                body: JSON.stringify({ source_day: sourceDay, csrf_token: this.csrfToken }),
            });
        }

        presetFulltime(days) {
            return this.request('/calendars/' + this.calendarId + '/preset/fulltime', {
                method: 'POST',
                headers: this.headers(),
                body: JSON.stringify({ days: days, csrf_token: this.csrfToken }),
            });
        }

        clearDay(weekday) {
            return this.request('/calendars/' + this.calendarId + '/day/' + weekday, {
                method: 'DELETE',
                headers: this.headers(),
            });
        }

        setDayWorking(weekday, isWorking) {
            return this.request('/calendars/' + this.calendarId + '/day/' + weekday, {
                method: 'PATCH',
                headers: this.headers(),
                body: JSON.stringify({ is_working: isWorking, csrf_token: this.csrfToken }),
            });
        }

        saveSettings(payload) {
            return this.request('/calendars/' + this.calendarId + '/settings', {
                method: 'PUT',
                headers: this.headers(),
                body: JSON.stringify(Object.assign({ csrf_token: this.csrfToken }, payload)),
            });
        }
    }

    global.CalendarApi = CalendarApi;
})(window);
