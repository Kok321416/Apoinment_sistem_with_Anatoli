(function () {
    var form = document.getElementById("paRescheduleForm");
    if (!form) return;
    var gridStart = parseInt(form.dataset.gridStart || "8", 10);
    var gridEnd = parseInt(form.dataset.gridEnd || "21", 10);
    var spanMin = (gridEnd - gridStart) * 60;
    var dragging = null;

    function snapTimeFromY(col, clientY) {
        var rect = col.getBoundingClientRect();
        var ratio = (clientY - rect.top) / rect.height;
        ratio = Math.max(0, Math.min(1, ratio));
        var minutes = Math.round((ratio * spanMin) / 30) * 30;
        minutes = Math.max(0, Math.min(spanMin - 30, minutes));
        var total = gridStart * 60 + minutes;
        var h = Math.floor(total / 60);
        var m = total % 60;
        return ("0" + h).slice(-2) + ":" + ("0" + m).slice(-2);
    }

    document.querySelectorAll(".pa-week__event[data-booking-id]").forEach(function (el) {
        el.setAttribute("draggable", "true");
        el.addEventListener("dragstart", function (e) {
            dragging = el;
            e.dataTransfer.setData("text/plain", el.dataset.bookingId || "");
            el.classList.add("is-dragging");
        });
        el.addEventListener("dragend", function () {
            el.classList.remove("is-dragging");
            dragging = null;
        });
    });

    document.querySelectorAll(".pa-week__col[data-date]").forEach(function (col) {
        col.addEventListener("dragover", function (e) {
            e.preventDefault();
            col.classList.add("is-drop-target");
        });
        col.addEventListener("dragleave", function () {
            col.classList.remove("is-drop-target");
        });
        col.addEventListener("drop", function (e) {
            e.preventDefault();
            col.classList.remove("is-drop-target");
            if (!dragging) return;
            var bookingId = dragging.dataset.bookingId;
            var newDate = col.dataset.date;
            var newTime = snapTimeFromY(col, e.clientY);
            if (!bookingId || !newDate) return;
            if (!window.confirm("Перенести запись #" + bookingId + " на " + newDate + " " + newTime + "?")) {
                return;
            }
            form.querySelector('[name="booking_id"]').value = bookingId;
            form.querySelector('[name="new_date"]').value = newDate;
            form.querySelector('[name="new_time"]').value = newTime;
            form.submit();
        });
    });
})();
