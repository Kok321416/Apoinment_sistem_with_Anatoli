(function () {
    "use strict";

    var root = document.getElementById("bookingRoot");
    var form = document.getElementById("publicBookForm");
    if (!root || !form) return;

    var serviceEl = document.getElementById("service_id");
    var dateEl = document.getElementById("booking_date");
    var slotsGrid = document.getElementById("slotsGrid");
    var slotsHint = document.getElementById("slotsHint");
    var timeEl = document.getElementById("booking_time");
    var endEl = document.getElementById("booking_end_time");
    var submitBtn = document.getElementById("bookSubmit");
    var windowsBlock = document.getElementById("windowsBlock");
    var windowsList = document.getElementById("windowsList");
    var dayPanelTitle = document.getElementById("dayPanelTitle");
    var slotsUrl = root.dataset.slotsUrl || "";
    var todayStr = root.dataset.today || "";
    var weeklyWindows = {};
    try {
        weeklyWindows = JSON.parse(root.dataset.weeklyWindows || "{}");
    } catch (e) {
        weeklyWindows = {};
    }

    var monthNames = [
        "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
        "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
    ];
    var currentCalDate = new Date();
    if (todayStr) {
        var parts = todayStr.split("-");
        if (parts.length === 3) {
            currentCalDate = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, 1);
        }
    }

    function weekdayIndex(dateObj) {
        var d = dateObj.getDay() - 1;
        return d < 0 ? 6 : d;
    }

    function hasWindows(weekday) {
        var list = weeklyWindows[String(weekday)] || weeklyWindows[weekday] || [];
        return Array.isArray(list) && list.length > 0;
    }

    function renderCalendar() {
        var y = currentCalDate.getFullYear();
        var m = currentCalDate.getMonth();
        var monthEl = document.getElementById("calMonthYear");
        if (monthEl) monthEl.textContent = monthNames[m] + " " + y;
        var first = new Date(y, m, 1);
        var last = new Date(y, m + 1, 0);
        var start = weekdayIndex(first);
        var today = new Date();
        today.setHours(0, 0, 0, 0);
        var selected = dateEl.value;
        var html = "";
        var i;
        for (i = 0; i < start; i++) {
            html += '<span class="booking-cal__day is-other"></span>';
        }
        for (var d = 1; d <= last.getDate(); d++) {
            var date = new Date(y, m, d);
            var cls = "booking-cal__day";
            var dateStr =
                date.getFullYear() +
                "-" +
                String(date.getMonth() + 1).padStart(2, "0") +
                "-" +
                String(d).padStart(2, "0");
            if (date < today) cls += " is-past";
            else if (date.getTime() === today.getTime()) cls += " is-today";
            if (hasWindows(weekdayIndex(date)) && date >= today) cls += " is-workday";
            if (selected && selected === dateStr) cls += " is-selected";
            var inner = '<span class="booking-cal__day-num">' + d + "</span>";
            if (hasWindows(weekdayIndex(date)) && date >= today) {
                inner += '<span class="booking-cal__dot" aria-hidden="true"></span>';
            }
            html +=
                '<button type="button" class="' +
                cls +
                '" data-date="' +
                dateStr +
                '"' +
                (hasWindows(weekdayIndex(date)) && date >= today
                    ? ' title="Есть окна приёма" aria-label="' + d + ', есть окна приёма"'
                    : ' aria-label="' + d + '"') +
                ">" +
                inner +
                "</button>";
        }
        var daysEl = document.getElementById("calDays");
        daysEl.innerHTML = html;
        daysEl.querySelectorAll(".booking-cal__day:not(.is-other):not(.is-past)").forEach(function (cell) {
            cell.addEventListener("click", function () {
                dateEl.value = cell.getAttribute("data-date") || "";
                renderCalendar();
                showDayWindows(dateEl.value);
                loadSlots();
            });
        });
    }

    function showDayWindows(dateStr) {
        windowsList.innerHTML = "";
        if (!dateStr) {
            windowsBlock.hidden = true;
            dayPanelTitle.textContent = "Выберите дату";
            return;
        }
        var dt = new Date(dateStr + "T00:00:00");
        dayPanelTitle.textContent =
            "День: " +
            dt.toLocaleDateString("ru-RU", { weekday: "long", day: "numeric", month: "long" });
        var list = weeklyWindows[String(weekdayIndex(dt))] || [];
        if (!list.length) {
            windowsBlock.hidden = false;
            windowsList.innerHTML = "<li class=\"text-muted\">В этот день специалист не указал окна приёма.</li>";
            return;
        }
        windowsBlock.hidden = false;
        list.forEach(function (w) {
            var li = document.createElement("li");
            li.textContent = (w.start_time || "") + " – " + (w.end_time || "");
            windowsList.appendChild(li);
        });
    }

    function loadSlots() {
        timeEl.value = "";
        endEl.value = "";
        submitBtn.disabled = true;
        slotsGrid.innerHTML = "";
        var sid = serviceEl.value;
        var date = dateEl.value;
        if (!sid || !date) {
            slotsHint.textContent = "Выберите услугу и день в календаре.";
            return;
        }
        slotsHint.textContent = "Загрузка слотов...";
        fetch(slotsUrl + "?date=" + encodeURIComponent(date) + "&service_id=" + encodeURIComponent(sid), {
            credentials: "same-origin",
        })
            .then(function (r) {
                return r.json();
            })
            .then(function (data) {
                var windows = data.available_windows || [];
                if (windows.length) {
                    windowsBlock.hidden = false;
                    windowsList.innerHTML = "";
                    windows.forEach(function (w) {
                        var li = document.createElement("li");
                        li.textContent = (w.start_time || "") + " – " + (w.end_time || "");
                        windowsList.appendChild(li);
                    });
                }
                var slots = data.available_slots || [];
                if (!slots.length) {
                    slotsHint.textContent = "Нет свободных слотов на эту дату.";
                    return;
                }
                slotsHint.textContent = "Выберите время:";
                slots.forEach(function (s) {
                    var btn = document.createElement("button");
                    btn.type = "button";
                    btn.className = "slot-btn";
                    btn.textContent = s.start_time + (s.end_time ? " – " + s.end_time : "");
                    btn.addEventListener("click", function () {
                        slotsGrid.querySelectorAll(".slot-btn").forEach(function (b) {
                            b.classList.remove("is-selected");
                        });
                        btn.classList.add("is-selected");
                        timeEl.value = s.start_time || "";
                        endEl.value = s.end_time || "";
                        submitBtn.disabled = false;
                    });
                    slotsGrid.appendChild(btn);
                });
            })
            .catch(function () {
                slotsHint.textContent = "Не удалось загрузить слоты.";
            });
    }

    document.getElementById("calPrev").addEventListener("click", function () {
        currentCalDate.setMonth(currentCalDate.getMonth() - 1);
        renderCalendar();
    });
    document.getElementById("calNext").addEventListener("click", function () {
        currentCalDate.setMonth(currentCalDate.getMonth() + 1);
        renderCalendar();
    });
    serviceEl.addEventListener("change", loadSlots);

    var submitting = false;
    form.addEventListener("submit", function (event) {
        if (submitting) {
            event.preventDefault();
            return;
        }
        if (!timeEl.value || !dateEl.value || !serviceEl.value) {
            event.preventDefault();
            slotsHint.textContent = "Выберите услугу, дату и время перед записью.";
            return;
        }
        submitting = true;
        submitBtn.disabled = true;
        submitBtn.textContent = "Записываем…";
        submitBtn.setAttribute("aria-busy", "true");
    });

    renderCalendar();
})();
