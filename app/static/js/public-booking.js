(function () {
    "use strict";

    var root = document.getElementById("bookingRoot");
    if (!root) return;

    var calendarId = root.dataset.calendarId;
    var selectedServiceId = null;
    var selectedDuration = 60;
    var currentCalDate = new Date();
    var monthNames = [
        "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
        "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
    ];

    function setStepState(step, state) {
        var el = document.querySelector('.booking-step[data-step="' + step + '"]');
        if (!el) return;
        el.classList.remove("is-active", "is-done");
        if (state) el.classList.add(state);
    }

    document.querySelectorAll(".booking-service").forEach(function (el) {
        el.addEventListener("click", function () {
            document.querySelectorAll(".booking-service").forEach(function (t) {
                t.classList.remove("is-selected");
            });
            this.classList.add("is-selected");
            selectedServiceId = this.dataset.serviceId;
            selectedDuration = parseInt(this.dataset.duration, 10) || 60;
            document.getElementById("service_id").value = selectedServiceId;
            setStepState("1", "is-done");
            setStepState("2", "is-active");
            var panel = document.getElementById("panelDate");
            if (panel) panel.classList.add("is-highlight");
            var dateVal = document.getElementById("booking_date").value;
            if (dateVal) loadTimeSlots();
        });
    });

    var serviceTiles = document.querySelectorAll(".booking-service");
    if (serviceTiles.length === 1) {
        var single = serviceTiles[0];
        single.classList.add("is-selected");
        selectedServiceId = single.dataset.serviceId;
        selectedDuration = parseInt(single.dataset.duration, 10) || 60;
        document.getElementById("service_id").value = selectedServiceId || "";
        setStepState("1", "is-done");
        setStepState("2", "is-active");
    } else {
        setStepState("1", "is-active");
    }

    function renderCalendar() {
        var y = currentCalDate.getFullYear();
        var m = currentCalDate.getMonth();
        document.getElementById("calMonthYear").textContent = monthNames[m] + " " + y;
        var first = new Date(y, m, 1);
        var last = new Date(y, m + 1, 0);
        var start = first.getDay() - 1;
        if (start < 0) start += 7;
        var today = new Date();
        today.setHours(0, 0, 0, 0);
        var html = "";
        var i;
        for (i = 0; i < start; i++) {
            html += '<span class="booking-cal__day is-other"></span>';
        }
        for (var d = 1; d <= last.getDate(); d++) {
            var date = new Date(y, m, d);
            var cls = "booking-cal__day";
            if (date < today) cls += " is-past";
            else if (date.getTime() === today.getTime()) cls += " is-today";
            var dateStr = date.getFullYear() + "-" + String(date.getMonth() + 1).padStart(2, "0") + "-" + String(d).padStart(2, "0");
            html += '<span class="' + cls + '" data-date="' + dateStr + '">' + d + "</span>";
        }
        document.getElementById("calDays").innerHTML = html;
        document.querySelectorAll("#calDays .booking-cal__day:not(.is-other):not(.is-past)").forEach(function (cell) {
            cell.addEventListener("click", function () {
                document.querySelectorAll("#calDays .booking-cal__day").forEach(function (c) {
                    c.classList.remove("is-selected");
                });
                this.classList.add("is-selected");
                document.getElementById("booking_date").value = this.dataset.date;
                setStepState("2", "is-done");
                setStepState("3", "is-active");
                var panel = document.getElementById("panelTime");
                if (panel) panel.classList.add("is-highlight");
                if (selectedServiceId) loadTimeSlots();
            });
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
    renderCalendar();

    function loadTimeSlots() {
        var date = document.getElementById("booking_date").value;
        var container = document.getElementById("timeSlots");
        var hint = document.getElementById("timeHint");
        var customRow = document.getElementById("timeCustomRow");
        document.getElementById("booking_time").value = "";
        document.getElementById("booking_end_time").value = "";
        document.getElementById("customTimeStart").value = "";

        if (!date || !selectedServiceId) {
            container.innerHTML = "";
            hint.textContent = "Сначала выберите услугу и дату";
            document.getElementById("timeWindows").hidden = true;
            document.getElementById("timeNoWindows").hidden = true;
            document.getElementById("timeEnterManual").hidden = true;
            document.getElementById("timeSubtitle").hidden = true;
            customRow.hidden = true;
            return;
        }

        hint.textContent = "Загрузка...";
        container.innerHTML = "";
        document.getElementById("timeNoWindows").hidden = true;
        document.getElementById("timeEnterManual").hidden = true;

        fetch("/book/" + calendarId + "/slots/?date=" + date + "&service_id=" + selectedServiceId)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.error) {
                    hint.textContent = data.error;
                    document.getElementById("timeWindows").hidden = true;
                    document.getElementById("timeNoWindows").hidden = true;
                    document.getElementById("timeEnterManual").hidden = true;
                    document.getElementById("timeSubtitle").hidden = true;
                    customRow.hidden = true;
                    return;
                }

                var slots = data.available_slots || [];
                var windows = data.available_windows || [];
                var windowsEl = document.getElementById("timeWindows");
                var subtitleEl = document.getElementById("timeSubtitle");
                var noWindowsEl = document.getElementById("timeNoWindows");
                var enterManualEl = document.getElementById("timeEnterManual");
                var customLabel = document.getElementById("timeCustomLabel");
                var customInput = document.getElementById("customTimeStart");

                if (windows.length === 0) {
                    hint.textContent = "";
                    windowsEl.hidden = true;
                    noWindowsEl.hidden = false;
                    noWindowsEl.innerHTML = "<strong>На эту дату приём не ведётся.</strong> Выберите другую дату.";
                    subtitleEl.hidden = true;
                    customRow.hidden = true;
                    container.innerHTML = "";
                    return;
                }

                windowsEl.hidden = false;
                windowsEl.innerHTML = "<strong>Приём:</strong> " +
                    windows.map(function (w) { return w.start_time + " – " + w.end_time; }).join("; ");

                if (slots.length === 0) {
                    hint.textContent = "";
                    subtitleEl.hidden = true;
                    enterManualEl.hidden = false;
                    enterManualEl.innerHTML = "<strong>Укажите время начала</strong> в пределах интервалов приёма.";
                    customRow.hidden = false;
                    customLabel.textContent = "Время начала:";
                    customInput.removeAttribute("min");
                    customInput.removeAttribute("max");
                    container.innerHTML = "";
                    return;
                }

                hint.textContent = "Длительность: " + selectedDuration + " мин. Выберите слот или укажите время.";
                subtitleEl.hidden = false;
                customRow.hidden = false;
                customLabel.textContent = "Или своё время:";
                customInput.min = "00:00";
                customInput.max = "23:59";
                container.innerHTML = "";

                slots.forEach(function (slot) {
                    var chip = document.createElement("button");
                    chip.type = "button";
                    chip.className = "booking-time-chip";
                    chip.textContent = slot.start_time;
                    chip.dataset.start = slot.start_time;
                    chip.dataset.end = slot.end_time;
                    chip.addEventListener("click", function () {
                        document.querySelectorAll(".booking-time-chip").forEach(function (c) {
                            c.classList.remove("is-selected");
                        });
                        this.classList.add("is-selected");
                        document.getElementById("booking_time").value = this.dataset.start;
                        document.getElementById("booking_end_time").value = this.dataset.end;
                        document.getElementById("customTimeStart").value = this.dataset.start;
                    });
                    container.appendChild(chip);
                });
            })
            .catch(function () {
                hint.textContent = "Ошибка загрузки слотов";
                customRow.hidden = true;
            });
    }

    document.getElementById("customTimeStart").addEventListener("change", function () {
        var v = this.value;
        if (!v) return;
        var parts = v.split(":").map(Number);
        var start = new Date(2000, 0, 1, parts[0], parts[1]);
        var end = new Date(start.getTime() + selectedDuration * 60000);
        var endStr = String(end.getHours()).padStart(2, "0") + ":" + String(end.getMinutes()).padStart(2, "0");
        document.getElementById("booking_time").value = v;
        document.getElementById("booking_end_time").value = endStr;
        document.querySelectorAll(".booking-time-chip").forEach(function (c) {
            c.classList.remove("is-selected");
        });
    });

    document.getElementById("bookingForm").addEventListener("submit", function (e) {
        if (!document.getElementById("service_id").value ||
            !document.getElementById("booking_date").value ||
            !document.getElementById("booking_time").value) {
            e.preventDefault();
            var panel = document.getElementById("panelTime");
            if (panel) panel.classList.add("is-error");
            hintFlash();
        }
    });

    function hintFlash() {
        var hint = document.getElementById("timeHint");
        if (hint) {
            hint.textContent = "Заполните услугу, дату и время перед отправкой";
            hint.style.color = "var(--accent-danger)";
        }
    }
})();

(function () {
    function formatPhone(value) {
        var digits = (value || "").replace(/\D/g, "");
        if (digits.charAt(0) === "8") digits = "7" + digits.slice(1);
        if (digits.charAt(0) !== "7") digits = "7" + digits;
        digits = digits.slice(0, 11);
        if (digits.length <= 1) return digits ? "+7" : "";
        return "+7 (" + digits.slice(1, 4) + ") " + digits.slice(4, 7) + "-" + digits.slice(7, 9) + "-" + digits.slice(9, 11);
    }
    function onPhoneInput(e) {
        var el = e.target;
        var start = el.selectionStart;
        var oldLen = el.value.length;
        el.value = formatPhone(el.value);
        var newStart = Math.max(0, start + (el.value.length - oldLen));
        el.setSelectionRange(newStart, newStart);
    }
    document.addEventListener("DOMContentLoaded", function () {
        ["login_phone", "client_phone"].forEach(function (id) {
            var el = document.getElementById(id);
            if (el) {
                el.addEventListener("input", onPhoneInput);
                if (el.value) el.value = formatPhone(el.value);
            }
        });
    });
})();
