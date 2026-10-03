(function () {
    "use strict";

    var form = document.getElementById("bookServiceForm");
    if (!form) return;

    var nextBtn = document.getElementById("bookServiceNext");
    var cards = form.querySelectorAll(".book-service-card");
    var radios = form.querySelectorAll('input[name="service_id"]');

    function selectedId() {
        var checked = form.querySelector('input[name="service_id"]:checked');
        return checked ? checked.value : "";
    }

    function sync() {
        var id = selectedId();
        cards.forEach(function (card) {
            var radio = card.querySelector('input[name="service_id"]');
            card.classList.toggle("is-selected", !!(radio && radio.checked));
        });
        if (nextBtn) nextBtn.disabled = !id;
    }

    radios.forEach(function (radio) {
        radio.addEventListener("change", sync);
    });
    cards.forEach(function (card) {
        card.addEventListener("click", function () {
            var radio = card.querySelector('input[name="service_id"]');
            if (!radio) return;
            radio.checked = true;
            sync();
        });
    });

    form.addEventListener("submit", function (event) {
        event.preventDefault();
        var id = selectedId();
        if (!id) return;
        var path = window.location.pathname.replace(/\/?$/, "/");
        var qs = window.location.search || "";
        window.location.href = path + "s/" + encodeURIComponent(id) + "/" + qs;
    });

    sync();
})();
