(function () {
    var monthNames = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
    var today = new Date();
    var current = { year: today.getFullYear(), month: today.getMonth() + 1 };
    var eventsByDate = {};

    function loadEvents() {
        var xhr = new XMLHttpRequest();
        xhr.open('GET', '/api/booking/calendar-events/?year=' + current.year + '&month=' + current.month, true);
        xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
        xhr.onload = function () {
            if (xhr.status !== 200) return;
            try {
                var data = JSON.parse(xhr.responseText);
                if (data.success && data.events) {
                    eventsByDate = {};
                    data.events.forEach(function (ev) {
                        if (!eventsByDate[ev.date]) eventsByDate[ev.date] = [];
                        eventsByDate[ev.date].push(ev);
                    });
                }
            } catch (e) {}
            renderCalendar();
        };
        xhr.send();
    }

    function renderCalendar() {
        var year = current.year;
        var month = current.month;
        var first = new Date(year, month - 1, 1);
        var last = new Date(year, month, 0);
        var startDay = (first.getDay() || 7) - 1;
        var daysInMonth = last.getDate();
        var prevMonth = month === 1 ? 12 : month - 1;
        var prevYear = month === 1 ? year - 1 : year;
        var prevLast = new Date(prevYear, prevMonth, 0);
        var daysPrev = prevLast.getDate();

        var titleText = monthNames[month - 1] + ' ' + year;
        var calTitleFullEl = document.getElementById('calTitleFull');
        if (calTitleFullEl) calTitleFullEl.textContent = titleText;

        var todayStr = today.getFullYear() + '-' + String(today.getMonth() + 1).padStart(2, '0') + '-' + String(today.getDate()).padStart(2, '0');
        var grid = document.getElementById('calGridFull');
        if (grid) {
            grid.innerHTML = '';
            var dayCount = 0;
            for (var i = 0; i < startDay; i++) {
                var dPrev = daysPrev - startDay + i + 1;
                var dateStrPrev = prevYear + '-' + String(prevMonth).padStart(2, '0') + '-' + String(dPrev).padStart(2, '0');
                grid.appendChild(makeDayCell(dateStrPrev, dPrev, true));
                dayCount++;
            }
            for (var d = 1; d <= daysInMonth; d++) {
                var dateStr = year + '-' + String(month).padStart(2, '0') + '-' + String(d).padStart(2, '0');
                var cell = makeDayCell(dateStr, d, false);
                if (dateStr === todayStr) cell.classList.add('today');
                grid.appendChild(cell);
                dayCount++;
            }
            var rest = (7 - (dayCount % 7)) % 7;
            var nextMonth = month === 12 ? 1 : month + 1;
            var nextYear = month === 12 ? year + 1 : year;
            for (var j = 1; j <= rest; j++) {
                var dateStrNext = nextYear + '-' + String(nextMonth).padStart(2, '0') + '-' + String(j).padStart(2, '0');
                grid.appendChild(makeDayCell(dateStrNext, j, true));
            }
        }
        renderMobileList();
    }

    var statusLabels = {
        confirmed: 'Подтверждена',
        pending: 'Ожидает',
        completed: 'Завершена',
        cancelled: 'Отменена'
    };

    function formatDayHeading(dateStr) {
        var parts = dateStr.split('-');
        if (parts.length !== 3) return dateStr;
        var d = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
        var weekdays = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];
        return Number(parts[2]) + ' ' + monthNames[Number(parts[1]) - 1].toLowerCase() + ', ' + weekdays[d.getDay()];
    }

    function eventAttrs(ev) {
        var timeStr = ev.time || '';
        if (ev.end_time) timeStr += ' - ' + ev.end_time;
        return 'class="cal-event ' + (ev.status || '') + '" data-id="' + ev.id + '" data-status="' + escapeAttr(ev.status || '') + '" data-calendar-id="' + (ev.calendar_id || '') + '" data-service-id="' + (ev.service_id || '') + '" data-client_name="' + escapeAttr(ev.client_name) + '" data-client_phone="' + escapeAttr(ev.client_phone) + '" data-client_email="' + escapeAttr(ev.client_email || '') + '" data-client_telegram="' + escapeAttr(ev.client_telegram || '') + '" data-time="' + escapeAttr(timeStr) + '" data-service="' + escapeAttr(ev.service || '') + '"';
    }

    function renderMobileList() {
        var list = document.getElementById('calMobileList');
        if (!list) return;
        var year = current.year;
        var month = current.month;
        var daysInMonth = new Date(year, month, 0).getDate();
        var html = [];
        var hasAny = false;
        for (var d = 1; d <= daysInMonth; d++) {
            var dateStr = year + '-' + String(month).padStart(2, '0') + '-' + String(d).padStart(2, '0');
            var events = (eventsByDate[dateStr] || []).slice();
            if (!events.length) continue;
            hasAny = true;
            events.sort(function (a, b) {
                return String(a.time || '').localeCompare(String(b.time || ''));
            });
            html.push('<section class="cal-mobile-day">');
            html.push('<h3 class="cal-mobile-day__title">' + formatDayHeading(dateStr) + '</h3>');
            html.push('<ul class="cal-mobile-day__list">');
            events.forEach(function (ev) {
                var status = (ev.status || '').toLowerCase();
                var label = statusLabels[status] || (ev.status || '');
                var timeStr = ev.time || '';
                if (ev.end_time) timeStr += ' - ' + ev.end_time;
                html.push('<li><button type="button" ' + eventAttrs(ev) + '>');
                html.push('<span class="cal-mobile-event__time">' + escapeAttr(timeStr) + '</span>');
                html.push('<span class="cal-mobile-event__main">');
                html.push('<span class="cal-mobile-event__name">' + escapeAttr(ev.client_name || '—') + '</span>');
                if (ev.service) html.push('<span class="cal-mobile-event__service">' + escapeAttr(ev.service) + '</span>');
                html.push('</span>');
                if (label) html.push('<span class="cal-mobile-event__status">' + escapeAttr(label) + '</span>');
                html.push('</button></li>');
            });
            html.push('</ul></section>');
        }
        if (!hasAny) {
            html.push('<p class="cal-mobile-list__empty">В этом месяце записей нет</p>');
        }
        list.innerHTML = html.join('');
    }

    function makeDayCell(dateStr, dayNum, otherMonth) {
        var cell = document.createElement('div');
        cell.className = 'calendar-day' + (otherMonth ? ' other-month' : '');
        cell.setAttribute('data-date', dateStr);
        var events = eventsByDate[dateStr] || [];
        var html = '<div class="day-num">' + dayNum + '</div>';
        if (events.length) {
            html += '<div class="day-dots">';
            events.slice(0, 4).forEach(function (ev) {
                html += '<span class="day-dot ' + (ev.status || '') + '"></span>';
            });
            html += '</div>';
        }
        html += '<div class="day-events">';
        events.forEach(function (ev) {
            html += '<div ' + eventAttrs(ev) + '>' + (ev.time || '') + ' ' + (ev.client_name || '') + '</div>';
        });
        html += '</div>';
        cell.innerHTML = html;
        return cell;
    }

    function escapeAttr(s) {
        return String(s || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function showPopover(ev, el) {
        var name = el.getAttribute('data-client_name') || '';
        var phone = el.getAttribute('data-client_phone') || '';
        var email = el.getAttribute('data-client_email') || '';
        var telegram = el.getAttribute('data-client_telegram') || '';
        var time = el.getAttribute('data-time') || '';
        var service = el.getAttribute('data-service') || '';
        var bookingId = el.getAttribute('data-id') || '';
        var status = (el.getAttribute('data-status') || '').toLowerCase();
        var pop = document.getElementById('eventPopover');
        if (!pop) return;

        var parts = ['<h4>' + (name || '—') + '</h4>'];
        if (time) parts.push('<p class="time">' + time + '</p>');
        if (service) parts.push('<p>Услуга: ' + service + '</p>');
        if (phone) parts.push('<p>Телефон: ' + phone + '</p>');
        if (email) parts.push('<p>Почта: ' + email + '</p>');
        if (telegram) parts.push('<p>Телеграм: ' + telegram + '</p>');

        var actionUrl = window.location.pathname + (window.location.search || '');
        var csrfEl = document.getElementById('csrfToken');
        var csrf = csrfEl ? csrfEl.value : '';
        var actionsHtml = [];
        if (bookingId && csrf) {
            actionsHtml.push('<div class="popover-actions">');
            if (status === 'pending') {
                actionsHtml.push('<form method="POST" action="' + escapeAttr(actionUrl) + '"><input type="hidden" name="csrf_token" value="' + escapeAttr(csrf) + '"><input type="hidden" name="action" value="confirm"><input type="hidden" name="booking_id" value="' + escapeAttr(bookingId) + '"><button type="submit" class="btn btn--success btn--sm">Подтвердить</button></form>');
            }
            if (status !== 'cancelled' && status !== 'completed') {
                actionsHtml.push('<form method="POST" action="' + escapeAttr(actionUrl) + '" onsubmit="return confirm(\'Отменить запись?\');"><input type="hidden" name="csrf_token" value="' + escapeAttr(csrf) + '"><input type="hidden" name="action" value="cancel"><input type="hidden" name="booking_id" value="' + escapeAttr(bookingId) + '"><button type="submit" class="btn btn--danger btn--sm">Отменить</button></form>');
            }
            if (status === 'confirmed') {
                actionsHtml.push('<form method="POST" action="' + escapeAttr(actionUrl) + '"><input type="hidden" name="csrf_token" value="' + escapeAttr(csrf) + '"><input type="hidden" name="action" value="complete"><input type="hidden" name="booking_id" value="' + escapeAttr(bookingId) + '"><button type="submit" class="btn btn--secondary btn--sm">Завершить</button></form>');
            }
            if (status !== 'cancelled' && status !== 'completed') {
                var calId = el.getAttribute('data-calendar-id') || '';
                var svcId = el.getAttribute('data-service-id') || '';
                actionsHtml.push('<button type="button" class="btn btn--ghost btn--sm btn-reschedule" data-booking-id="' + escapeAttr(bookingId) + '" data-calendar-id="' + escapeAttr(calId) + '" data-service-id="' + escapeAttr(svcId) + '">Перенести</button>');
            }
            actionsHtml.push('</div>');
        }
        parts.push(actionsHtml.join(''));
        pop.innerHTML = parts.join('');
        pop.hidden = false;
        pop.style.display = 'block';
        var rect = el.getBoundingClientRect();
        pop.style.left = (rect.left + window.scrollX) + 'px';
        pop.style.top = (rect.bottom + 4 + window.scrollY) + 'px';
        if (rect.left + 320 > window.innerWidth) pop.style.left = (rect.right - 320 + window.scrollX) + 'px';
    }

    function hidePopover() {
        var pop = document.getElementById('eventPopover');
        if (pop) {
            pop.style.display = 'none';
            pop.hidden = true;
        }
    }

    function goPrev() {
        if (current.month === 1) { current.year--; current.month = 12; } else current.month--;
        loadEvents();
    }

    function goNext() {
        if (current.month === 12) { current.year++; current.month = 1; } else current.month++;
        loadEvents();
    }

    function initUi() {
        var calPrevFull = document.getElementById('calPrevFull');
        var calNextFull = document.getElementById('calNextFull');
        if (calPrevFull) calPrevFull.onclick = goPrev;
        if (calNextFull) calNextFull.onclick = goNext;

        function onCalEventClick(e) {
            var el = e.target.closest('.cal-event');
            if (el) showPopover(e, el);
        }
        var calGridFullEl = document.getElementById('calGridFull');
        if (calGridFullEl) calGridFullEl.addEventListener('click', onCalEventClick);
        var calMobileListEl = document.getElementById('calMobileList');
        if (calMobileListEl) calMobileListEl.addEventListener('click', onCalEventClick);

        document.addEventListener('click', function (e) {
            if (!e.target.closest('.cal-event') && !e.target.closest('#eventPopover')) hidePopover();
        });

        var viewList = document.getElementById('viewList');
        var viewCalendar = document.getElementById('viewCalendar');
        var listCol = document.getElementById('bookingListCol');
        var listPlaceholder = document.getElementById('bookingListColPlaceholder');
        var layoutList = viewList ? viewList.querySelector('.booking-page-layout') : null;
        var pageContainer = document.getElementById('bookingPageContainer');

        document.querySelectorAll('.bookings-segment__btn, .view-switcher-btn').forEach(function (btn) {
            btn.onclick = function () {
                var v = this.getAttribute('data-view');
                document.querySelectorAll('.bookings-segment__btn, .view-switcher-btn').forEach(function (b) {
                    b.classList.remove('is-active');
                    b.setAttribute('aria-selected', 'false');
                });
                this.classList.add('is-active');
                this.setAttribute('aria-selected', 'true');
                if (v === 'calendar') {
                    if (viewList) viewList.classList.remove('is-active');
                    if (viewCalendar) viewCalendar.classList.add('is-active');
                    if (listPlaceholder && listCol) listPlaceholder.appendChild(listCol);
                    if (pageContainer) pageContainer.classList.add('is-calendar-view');
                } else {
                    if (viewCalendar) viewCalendar.classList.remove('is-active');
                    if (viewList) viewList.classList.add('is-active');
                    if (pageContainer) pageContainer.classList.remove('is-calendar-view');
                    if (listCol && layoutList && listCol.parentNode !== layoutList) layoutList.appendChild(listCol);
                }
            };
        });

        loadEvents();

        var rescheduleBookingId = null;
        var rescheduleCalendarId = null;
        var rescheduleServiceId = null;
        var overlay = document.getElementById('rescheduleOverlay');
        var modal = document.querySelector('.reschedule-modal');
        var lastFocus = null;
        var focusTrapHandler = null;

        function getFocusable(container) {
            if (!container) return [];
            return Array.prototype.slice.call(container.querySelectorAll(
                'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
            )).filter(function (el) {
                return !el.hasAttribute('disabled') && el.getAttribute('aria-hidden') !== 'true';
            });
        }

        function openRescheduleModal(bookingId, calendarId, serviceId) {
            rescheduleBookingId = bookingId;
            rescheduleCalendarId = calendarId;
            rescheduleServiceId = serviceId;
            document.getElementById('rescheduleBookingId').value = bookingId;
            document.getElementById('rescheduleNewDate').value = '';
            document.getElementById('rescheduleNewTime').value = '';
            document.getElementById('rescheduleDate').value = '';
            document.getElementById('rescheduleSlots').innerHTML = '';
            document.getElementById('rescheduleSubmit').disabled = true;
            lastFocus = document.activeElement;
            if (overlay) {
                overlay.hidden = false;
                overlay.classList.add('is-open');
            }
            hidePopover();
            if (focusTrapHandler) {
                document.removeEventListener('keydown', focusTrapHandler);
            }
            focusTrapHandler = function (e) {
                if (e.key !== 'Tab' || !overlay || !overlay.classList.contains('is-open')) return;
                var focusable = getFocusable(modal);
                if (!focusable.length) return;
                var first = focusable[0];
                var last = focusable[focusable.length - 1];
                if (e.shiftKey && document.activeElement === first) {
                    e.preventDefault();
                    last.focus();
                } else if (!e.shiftKey && document.activeElement === last) {
                    e.preventDefault();
                    first.focus();
                }
            };
            document.addEventListener('keydown', focusTrapHandler);
            var dateEl = document.getElementById('rescheduleDate');
            if (dateEl) dateEl.focus();
        }

        function closeRescheduleModal() {
            if (overlay) {
                overlay.classList.remove('is-open');
                overlay.hidden = true;
            }
            if (focusTrapHandler) {
                document.removeEventListener('keydown', focusTrapHandler);
                focusTrapHandler = null;
            }
            if (lastFocus && typeof lastFocus.focus === 'function') {
                lastFocus.focus();
            }
            lastFocus = null;
        }

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && overlay && overlay.classList.contains('is-open')) {
                closeRescheduleModal();
            }
            if (e.key === 'Escape') hidePopover();
        });

        document.addEventListener('click', function (e) {
            var btn = e.target.closest('.btn-reschedule');
            if (btn && btn.dataset.bookingId) {
                e.preventDefault();
                openRescheduleModal(btn.dataset.bookingId, btn.dataset.calendarId || '', btn.dataset.serviceId || '');
            }
        });

        var cancelBtn = document.getElementById('rescheduleCancel');
        if (cancelBtn) cancelBtn.onclick = closeRescheduleModal;
        if (overlay) {
            overlay.onclick = function (e) {
                if (e.target === overlay) closeRescheduleModal();
            };
        }
        if (modal) modal.onclick = function (e) { e.stopPropagation(); };

        var dateInput = document.getElementById('rescheduleDate');
        if (dateInput) {
            dateInput.addEventListener('change', function () {
                var dateVal = this.value;
                document.getElementById('rescheduleNewTime').value = '';
                document.getElementById('rescheduleSubmit').disabled = true;
                var slotsEl = document.getElementById('rescheduleSlots');
                slotsEl.innerHTML = '';
                if (!dateVal || !rescheduleCalendarId || !rescheduleServiceId) return;
                var url = '/book/' + rescheduleCalendarId + '/slots/?date=' + encodeURIComponent(dateVal) + '&service_id=' + encodeURIComponent(rescheduleServiceId) + '&exclude_booking_id=' + encodeURIComponent(rescheduleBookingId || '');
                var xhr = new XMLHttpRequest();
                xhr.open('GET', url, true);
                xhr.onload = function () {
                    if (xhr.status !== 200) return;
                    try {
                        var data = JSON.parse(xhr.responseText);
                        var slots = data.available_slots || [];
                        slots.forEach(function (s) {
                            var slotBtn = document.createElement('button');
                            slotBtn.type = 'button';
                            slotBtn.className = 'slot-btn';
                            slotBtn.textContent = s.start_time + (s.end_time ? ' – ' + s.end_time : '');
                            slotBtn.dataset.time = s.start_time || '';
                            slotBtn.onclick = function () {
                                document.querySelectorAll('#rescheduleSlots .slot-btn').forEach(function (b) { b.classList.remove('is-selected'); });
                                slotBtn.classList.add('is-selected');
                                document.getElementById('rescheduleNewTime').value = slotBtn.dataset.time;
                                document.getElementById('rescheduleSubmit').disabled = false;
                            };
                            slotsEl.appendChild(slotBtn);
                        });
                        if (slots.length === 0) slotsEl.innerHTML = '<span class="text-muted">Нет доступных слотов на эту дату</span>';
                    } catch (err) {}
                };
                xhr.send();
            });
        }

        var rescheduleForm = document.getElementById('rescheduleForm');
        if (rescheduleForm) {
            rescheduleForm.onsubmit = function () {
                document.getElementById('rescheduleNewDate').value = document.getElementById('rescheduleDate').value;
            };
        }

        initBookingsHubFilters();
        initNextBookingCountdown();
        initBookingsFab();
    }

    function initBookingsHubFilters() {
        var searchEl = document.getElementById('bookings-search');
        var quickPills = document.querySelectorAll('.bookings-quick-pill');
        var todayIsoEl = document.getElementById('bookingsTodayIso');
        var todayIso = todayIsoEl ? todayIsoEl.value : '';
        var dateFilter = 'all';

        function addDays(iso, days) {
            if (!iso) return '';
            var p = iso.split('-');
            var d = new Date(parseInt(p[0], 10), parseInt(p[1], 10) - 1, parseInt(p[2], 10));
            d.setDate(d.getDate() + days);
            return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
        }

        var tomorrowIso = addDays(todayIso, 1);
        var weekEndIso = addDays(todayIso, 6);

        function matchDate(cardDate) {
            if (dateFilter === 'all') return true;
            if (!cardDate || !todayIso) return true;
            if (dateFilter === 'today') return cardDate === todayIso;
            if (dateFilter === 'tomorrow') return cardDate === tomorrowIso;
            if (dateFilter === 'week') return cardDate >= todayIso && cardDate <= weekEndIso;
            return true;
        }

        function filterBookings() {
            var q = (searchEl && searchEl.value || '').trim().toLowerCase();
            var cards = Array.from(document.querySelectorAll('.bkg-card'));
            var visibleCount = 0;

            cards.forEach(function (card) {
                var searchText = card.getAttribute('data-search') || '';
                var cardDate = card.getAttribute('data-date') || '';
                var show = (!q || searchText.indexOf(q) !== -1) && matchDate(cardDate);
                card.classList.toggle('is-hidden', !show);
                if (show) visibleCount++;
            });

            document.querySelectorAll('.bookings-day-group').forEach(function (group) {
                var visibleInGroup = group.querySelectorAll('.bkg-card:not(.is-hidden)').length;
                group.classList.toggle('is-hidden', visibleInGroup === 0);
            });

            var pastSection = document.getElementById('bookings-past-section');
            if (pastSection) {
                var pastVisible = pastSection.querySelectorAll('.bkg-card:not(.is-hidden)').length;
                pastSection.classList.toggle('is-hidden', pastVisible === 0);
            }

            var empty = document.getElementById('bookings-filter-empty');
            if (empty) empty.hidden = visibleCount > 0 || cards.length === 0;
        }

        if (searchEl) searchEl.addEventListener('input', filterBookings);
        quickPills.forEach(function (pill) {
            pill.addEventListener('click', function () {
                quickPills.forEach(function (p) { p.classList.remove('is-active'); });
                pill.classList.add('is-active');
                dateFilter = pill.getAttribute('data-date-filter') || 'all';
                filterBookings();
            });
        });
    }

    function initNextBookingCountdown() {
        var el = document.getElementById('bookings-next-countdown');
        if (!el) return;
        var mins = parseInt(el.getAttribute('data-minutes') || '0', 10);
        if (mins <= 0) {
            el.textContent = 'Скоро начнётся';
            return;
        }
        if (mins < 60) {
            el.textContent = 'через ' + mins + ' мин.';
            return;
        }
        var hours = Math.floor(mins / 60);
        var rest = mins % 60;
        el.textContent = rest ? ('через ' + hours + ' ч. ' + rest + ' мин.') : ('через ' + hours + ' ч.');
    }

    function initBookingsFab() {
        var fab = document.getElementById('bookings-fab');
        if (!fab) return;
        fab.addEventListener('click', function () {
            if (typeof window.showToast === 'function') {
                window.showToast('Ручное создание записи скоро будет доступно', 'success');
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initUi);
    } else {
        initUi();
    }
})();
