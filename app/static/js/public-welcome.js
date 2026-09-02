(function () {
    "use strict";

    var form = document.getElementById("welcomeContactForm");
    if (!form) {
        return;
    }

    var lookupUrl = form.dataset.lookupUrl || "";
    var phoneInput = document.getElementById("phone");
    var telegramInput = document.getElementById("telegram");
    var fioInput = document.getElementById("fio");
    var note = document.getElementById("welcomeReturningNote");
    var timer = null;
    var lastKey = "";

    function showNote(message) {
        if (!note || !message) {
            return;
        }
        note.textContent = message;
        note.hidden = false;
    }

    function fillIfEmpty(input, value) {
        if (!input || !value) {
            return;
        }
        if (!(input.value || "").trim()) {
            input.value = value;
        }
    }

    function runLookup() {
        if (!lookupUrl) {
            return;
        }
        var phone = phoneInput ? phoneInput.value.trim() : "";
        var telegram = telegramInput ? telegramInput.value.trim() : "";
        if (!phone && !telegram) {
            return;
        }
        var key = phone + "|" + telegram;
        if (key === lastKey) {
            return;
        }
        lastKey = key;

        var params = new URLSearchParams();
        if (phone) {
            params.set("phone", phone);
        }
        if (telegram) {
            params.set("telegram", telegram);
        }

        fetch(lookupUrl + "?" + params.toString(), {
            headers: { Accept: "application/json" },
            credentials: "same-origin",
        })
            .then(function (r) {
                return r.json();
            })
            .then(function (data) {
                if (!data || !data.found) {
                    return;
                }
                fillIfEmpty(fioInput, data.name);
                fillIfEmpty(phoneInput, data.phone);
                fillIfEmpty(telegramInput, data.telegram ? "@" + data.telegram.replace(/^@/, "") : "");
                showNote(data.message || "Вы уже заходили — данные подставлены.");
            })
            .catch(function () {
                /* lookup is optional UX */
            });
    }

    function scheduleLookup() {
        if (timer) {
            clearTimeout(timer);
        }
        timer = setTimeout(runLookup, 450);
    }

    if (phoneInput) {
        phoneInput.addEventListener("input", scheduleLookup);
        phoneInput.addEventListener("blur", runLookup);
    }
    if (telegramInput) {
        telegramInput.addEventListener("input", scheduleLookup);
        telegramInput.addEventListener("blur", runLookup);
    }
})();
