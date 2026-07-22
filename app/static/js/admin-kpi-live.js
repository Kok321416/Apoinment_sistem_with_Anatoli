(function () {
    var grid = document.getElementById("paKpiLive");
    if (!grid) return;

    function applyKpi(kpi) {
        Object.keys(kpi).forEach(function (key) {
            var el = grid.querySelector('[data-kpi="' + key + '"]');
            if (el) el.textContent = kpi[key];
        });
    }

    function fetchOnce() {
        fetch("/platform-admin/api/kpi/", { credentials: "same-origin", headers: { Accept: "application/json" } })
            .then(function (r) { return r.json(); })
            .then(applyKpi)
            .catch(function () {});
    }

    if (typeof EventSource !== "undefined") {
        var es = new EventSource("/platform-admin/api/kpi/stream/");
        es.onmessage = function (ev) {
            try {
                applyKpi(JSON.parse(ev.data));
            } catch (e) { /* ignore */ }
        };
        es.onerror = function () {
            es.close();
            fetchOnce();
            setInterval(fetchOnce, 60000);
        };
    } else {
        fetchOnce();
        setInterval(fetchOnce, 60000);
    }
})();
