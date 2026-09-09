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
    var calendarTz = root.dataset.calendarTz || "Asia/Irkutsk";
    var calendarTzLabel = root.dataset.calendarTzLabel || calendarTz;
    var clientTzEl = document.getElementById("client_timezone");
    var viewerTzHint = document.getElementById("viewerTzHint");
    var viewerTz = "";
    try {
        viewerTz = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
    } catch (e) {
        viewerTz = "";
    }
    if (clientTzEl && viewerTz) {
        clientTzEl.value = viewerTz;
    }
    if (viewerTzHint && viewerTz && viewerTz !== calendarTz) {
        viewerTzHint.hidden = false;
        viewerTzHint.textContent =
            "Ваш пояс: " + viewerTz + ". Ниже у выбранного слота будет показано ваше локальное время.";
    }
    var weeklyWindows = {};
    try {
        weeklyWindows = JSON.parse(root.dataset.weeklyWindows || "{}");
    } catch (e) {
        weeklyWindows = {};
    }

    function formatInTz(dateStr, timeStr, timeZone) {
        if (!dateStr || !timeStr || !timeZone) return "";
        try {
            var iso = dateStr + "T" + timeStr + ":00";
            // Interpret wall-clock in calendar TZ via temporal offset trick:
            // build Instant by formatting parts in calendar zone is hard without libs;
            // use Date with explicit offset from Intl when possible.
            var probe = new Date(iso + "Z");
            if (isNaN(probe.getTime())) return "";
            // Better: use Intl with formatToParts on a Date constructed from UTC guess then adjust.
            // Simpler approach for modern browsers: Temporal if available, else approximate via
            // locale string parsing of the calendar-local instant.
            var formatter = new Intl.DateTimeFormat("en-US", {
                timeZone: calendarTz,
                year: "numeric",
                month: "2-digit",
                day: "2-digit",
                hour: "2-digit",
                minute: "2-digit",
                hour12: false,
            });
            // Find UTC ms such that calendarTz wall clock matches dateStr/timeStr.
            var target = dateStr + " " + timeStr;
            var guess = Date.parse(dateStr + "T" + timeStr + ":00Z");
            if (isNaN(guess)) return "";
            var best = guess;
            for (var i = 0; i < 3; i++) {
                var parts = formatter.formatToParts(new Date(best));
                var map = {};
                parts.forEach(function (p) {
                    if (p.type !== "literal") map[p.type] = p.value;
                });
                var got =
                    map.year +
                    "-" +
                    map.month +
                    "-" +
                    map.day +
                    " " +
                    map.hour.replace(/^24$/, "00") +
                    ":" +
                    map.minute;
                var wantY = parseInt(dateStr.slice(0, 4), 10);
                var wantM = parseInt(dateStr.slice(5, 7), 10);
                var wantD = parseInt(dateStr.slice(8, 10), 10);
                var wantH = parseInt(timeStr.slice(0, 2), 10);
                var wantMin = parseInt(timeStr.slice(3, 5), 10);
                var gotY = parseInt(map.year, 10);
                var gotM = parseInt(map.month, 10);
                var gotD = parseInt(map.day, 10);
                var gotH = parseInt(map.hour.replace(/^24$/, "00"), 10);
                var gotMin = parseInt(map.minute, 10);
                var deltaMin =
                    ((wantY - gotY) * 525600 +
                        (wantM - gotM) * 43800 +
                        (wantD - gotD) * 1440 +
                        (wantH - gotH) * 60 +
                        (wantMin - gotMin));
                best += deltaMin * 60 * 1000;
                if (got === target || Math.abs(deltaMin) < 1) break;
            }
            var outFmt = new Intl.DateTimeFormat("ru-RU", {
                timeZone: timeZone,
                hour: "2-digit",
                minute: "2-digit",
                hour12: false,
            });
            return outFmt.format(new Date(best)).replace(",", "");
        } catch (err) {
            return "";
        }
    }

    function updateReviewDual() {
        var review = document.getElementById("bookReviewText");
        if (!review || !dateEl.value || !timeEl.value) return;
        var base =
            "Услуга, дата и время специалиста: " +
            dateEl.value +
            " " +
            timeEl.value +
            (endEl.value ? "–" + endEl.value : "") +
            " (" +
            calendarTzLabel +
            ")";
        if (viewerTz && viewerTz !== calendarTz) {
            var localStart = formatInTz(dateEl.value, timeEl.value, viewerTz);
            var localEnd = endEl.value ? formatInTz(dateEl.value, endEl.value, viewerTz) : "";
            if (localStart) {
                base +=
                    ". У вас: " +
                    localStart +
                    (localEnd ? "–" + localEnd : "") +
                    " (" +
                    viewerTz +
                    ")";
            }
        }
        review.textContent = base;
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
                setWizardStep(3);
            });
        });
    }

    function showDayWindows(dateStr) {
        windowsList.innerHTML = "";
        if (!dateStr) {
            windowsBlock.hidden = true;
            dayPanelTitle.textContent = "Сначала выберите дату в календаре";
            return;
        }
        var dt = new Date(dateStr + "T00:00:00");
        dayPanelTitle.textContent =
            "Дата: " +
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

    function showSlotsEmptyMessage() {
        slotsGrid.innerHTML =
            '<p class="slots-empty-message" role="alert">Нет свободных слотов на эту дату</p>';
        slotsHint.textContent = "";
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
                    showSlotsEmptyMessage();
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
                        var reviewBlock = document.getElementById("bookReview");
                        if (reviewBlock) reviewBlock.hidden = false;
                        updateReviewDual();
                        setProgressStep(4);
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
    serviceEl.addEventListener("change", function () {
        loadSlots();
        if (serviceEl.value) {
            scrollToStep(2);
            setProgressStep(2);
        }
    });

    function isWizard() {
        return (
            window.matchMedia("(max-width: 1024px)").matches ||
            document.body.classList.contains("tg-webapp") ||
            document.documentElement.classList.contains("tg-webapp")
        );
    }

    function setWizardStep(step) {
        setProgressStep(step);
        document.querySelectorAll("[data-book-step]").forEach(function (panel) {
            var n = parseInt(panel.getAttribute("data-book-step"), 10);
            panel.classList.toggle("is-step-active", n === step);
        });
        if (isWizard()) {
            var el = document.querySelector('[data-book-step="' + step + '"]');
            if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
        }
    }

    function scrollToStep(step) {
        setWizardStep(step);
    }

    function setProgressStep(step) {
        var bar = document.getElementById("bookCalProgress");
        if (!bar) return;
        bar.querySelectorAll(".book-cal-progress__item").forEach(function (btn) {
            var n = parseInt(btn.getAttribute("data-step"), 10);
            btn.classList.toggle("is-active", n === step);
            btn.classList.toggle("is-done", n < step);
        });
    }

    (function wireProgress() {
        var bar = document.getElementById("bookCalProgress");
        if (!bar) return;
        bar.querySelectorAll(".book-cal-progress__item").forEach(function (btn) {
            btn.addEventListener("click", function () {
                var step = parseInt(btn.getAttribute("data-step"), 10);
                if (step === 2 && !serviceEl.value) {
                    slotsHint.textContent = "Сначала выберите услугу.";
                    setWizardStep(1);
                    return;
                }
                if (step === 3 && !dateEl.value) {
                    slotsHint.textContent = "Сначала выберите дату в календаре.";
                    setWizardStep(2);
                    return;
                }
                setWizardStep(step);
            });
        });
        setWizardStep(1);
        if (!("IntersectionObserver" in window) || isWizard()) return;
        var panels = [
            document.getElementById("bookStepService"),
            document.getElementById("bookStepDate"),
            document.getElementById("bookStepTime"),
        ].filter(Boolean);
        var observer = new IntersectionObserver(
            function (entries) {
                entries.forEach(function (entry) {
                    if (!entry.isIntersecting) return;
                    var step = parseInt(entry.target.getAttribute("data-book-step"), 10);
                    if (step) setProgressStep(step);
                });
            },
            { root: null, rootMargin: "-30% 0px -45% 0px", threshold: 0.05 }
        );
        panels.forEach(function (p) {
            observer.observe(p);
        });
    })();

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
