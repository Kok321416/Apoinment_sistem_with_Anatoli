(function (global) {
    "use strict";

    function formatRelative(iso) {
        if (!iso) return "—";
        try {
            var d = new Date(iso);
            var diff = Date.now() - d.getTime();
            var mins = Math.floor(diff / 60000);
            if (mins < 1) return "только что";
            if (mins < 60) return mins + " мин. назад";
            var hours = Math.floor(mins / 60);
            if (hours < 24) return hours + " ч. назад";
            var days = Math.floor(hours / 24);
            if (days === 1) return "вчера";
            if (days < 7) return days + " дн. назад";
            return d.toLocaleDateString("ru-RU");
        } catch (e) {
            return iso;
        }
    }

    function formatRelativeFuture(iso) {
        if (!iso) return "Нет записей";
        try {
            var d = new Date(iso + "T12:00:00");
            var today = new Date();
            today.setHours(0, 0, 0, 0);
            var diff = today - d;
            var days = Math.floor(diff / 86400000);
            if (days === 0) return "сегодня";
            if (days === 1) return "вчера";
            if (days < 7) return days + " дн. назад";
            if (days < 30) return Math.floor(days / 7) + " нед. назад";
            return d.toLocaleDateString("ru-RU");
        } catch (e) {
            return iso;
        }
    }

    function loadData() {
        var node = document.getElementById("calendars-hub-data");
        if (!node) return { dashboard: {}, calendars: [], activity: [] };
        try {
            return JSON.parse(node.textContent || "{}");
        } catch (e) {
            return { dashboard: {}, calendars: [], activity: [] };
        }
    }

    function openCreateForm() {
        var panel = document.getElementById("calendars-create");
        var toggle = document.getElementById("calendars-create-toggle");
        if (panel) {
            panel.hidden = false;
            var input = panel.querySelector("#calendar_name");
            if (input) input.focus();
        }
        if (toggle) toggle.hidden = true;
    }

    function closeCreateForm() {
        var panel = document.getElementById("calendars-create");
        var toggle = document.getElementById("calendars-create-toggle");
        if (panel) panel.hidden = true;
        if (toggle) toggle.hidden = false;
    }

    function filterCalendars() {
        var search = (document.getElementById("calendars-search") || {}).value || "";
        var filter = (document.getElementById("calendars-filter") || {}).value || "all";
        var sort = (document.getElementById("calendars-sort") || {}).value || "recent";
        var q = search.trim().toLowerCase();
        var cards = Array.from(document.querySelectorAll(".cal-card"));
        var visible = [];

        cards.forEach(function (card) {
            var status = card.getAttribute("data-status") || "";
            var isArchive = card.getAttribute("data-archive") === "true";
            var searchText = card.getAttribute("data-search") || "";
            var matchSearch = !q || searchText.indexOf(q) !== -1;
            var matchFilter = true;
            if (filter === "active") matchFilter = status === "active";
            else if (filter === "inactive") matchFilter = status === "inactive" && !isArchive;
            else if (filter === "archive") matchFilter = isArchive;
            var show = matchSearch && matchFilter;
            card.classList.toggle("is-hidden", !show);
            if (show) visible.push(card);
        });

        visible.sort(function (a, b) {
            if (sort === "name") {
                return (a.getAttribute("data-name") || "").localeCompare(b.getAttribute("data-name") || "", "ru");
            }
            if (sort === "created") {
                return (b.getAttribute("data-created") || "").localeCompare(a.getAttribute("data-created") || "");
            }
            if (sort === "activity") {
                var aa = parseInt(a.getAttribute("data-activity") || "0", 10);
                var ab = parseInt(b.getAttribute("data-activity") || "0", 10);
                return ab - aa;
            }
            return (b.getAttribute("data-updated") || "").localeCompare(a.getAttribute("data-updated") || "");
        });

        var grid = document.getElementById("calendars-grid");
        if (grid) {
            visible.forEach(function (card) {
                grid.appendChild(card);
            });
        }

        var empty = document.getElementById("calendars-filter-empty");
        if (empty) empty.hidden = visible.length > 0 || cards.length === 0;
    }

    function initRelativeDates() {
        document.querySelectorAll("[data-relative]").forEach(function (el) {
            var iso = el.getAttribute("data-relative");
            if (!iso) return;
            if (el.classList.contains("cal-card__meta-value--booking")) {
                el.textContent = formatRelativeFuture(iso);
            } else {
                el.textContent = formatRelative(iso);
            }
        });
    }

    function initHero(dashboard) {
        var updated = document.getElementById("calendars-hero-updated");
        if (updated && dashboard.last_updated) {
            updated.textContent = "Последнее изменение: " + formatRelative(dashboard.last_updated);
        }
    }

    function stubAction(message) {
        if (typeof global.showToast === "function") {
            global.showToast(message, "success");
        } else {
            window.alert(message);
        }
    }

    function init() {
        var page = document.getElementById("calendars-page");
        if (!page) return;

        var data = loadData();
        initHero(data.dashboard || {});
        initRelativeDates();

        document.getElementById("btn-new-calendar") && document.getElementById("btn-new-calendar").addEventListener("click", openCreateForm);
        document.getElementById("btn-hero-new-calendar") && document.getElementById("btn-hero-new-calendar").addEventListener("click", openCreateForm);
        document.getElementById("btn-empty-create") && document.getElementById("btn-empty-create").addEventListener("click", openCreateForm);
        document.getElementById("calendars-create-toggle") && document.getElementById("calendars-create-toggle").addEventListener("click", openCreateForm);
        document.getElementById("btn-close-create") && document.getElementById("btn-close-create").addEventListener("click", closeCreateForm);

        document.getElementById("btn-import-calendars") && document.getElementById("btn-import-calendars").addEventListener("click", function () {
            stubAction("Импорт календарей скоро будет доступен");
        });
        document.getElementById("btn-export-calendars") && document.getElementById("btn-export-calendars").addEventListener("click", function () {
            stubAction("Экспорт календарей скоро будет доступен");
        });
        document.getElementById("btn-public-qr") && document.getElementById("btn-public-qr").addEventListener("click", function () {
            stubAction("QR-код скоро будет доступен");
        });

        document.querySelectorAll("[data-stub-stats]").forEach(function (btn) {
            btn.addEventListener("click", function () {
                stubAction("Статистика календаря скоро будет доступна");
            });
        });

        var search = document.getElementById("calendars-search");
        var filter = document.getElementById("calendars-filter");
        var sort = document.getElementById("calendars-sort");
        if (search) search.addEventListener("input", filterCalendars);
        if (filter) filter.addEventListener("change", filterCalendars);
        if (sort) sort.addEventListener("change", filterCalendars);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})(window);
