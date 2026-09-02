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
    var consent = document.getElementById("welcomeConsent");
    var note = document.getElementById("welcomeReturningNote");
    var fioError = document.getElementById("fioError");
    var phoneError = document.getElementById("phoneError");
    var privacyError = document.getElementById("privacyError");
    var timer = null;
    var lastKey = "";

    function showNote(message) {
        if (!note || !message) {
            return;
        }
        note.textContent = message;
        note.hidden = false;
    }

    function setFieldError(input, errorEl, message, on) {
        if (input) {
            input.classList.toggle("is-invalid", on);
        }
        if (errorEl) {
            if (on && message) {
                errorEl.textContent = message;
            }
            errorEl.hidden = !on;
        }
    }

    function clearErrors() {
        setFieldError(fioInput, fioError, "", false);
        setFieldError(phoneInput, phoneError, "", false);
        if (privacyError) {
            privacyError.hidden = true;
        }
        if (consent) {
            consent.classList.remove("is-invalid");
        }
    }

    function digitsOnlyPhone(value) {
        return (value || "").replace(/\D/g, "");
    }

    function isValidPhone(value) {
        var digits = digitsOnlyPhone(value);
        return digits.length === 11 && digits.charAt(0) === "7";
    }

    function isValidFio(value) {
        return (value || "").trim().length >= 3;
    }

    function validateForm() {
        clearErrors();
        var ok = true;

        if (!isValidFio(fioInput && fioInput.value)) {
            setFieldError(fioInput, fioError, "Укажите фамилию и имя полностью.", true);
            ok = false;
        }
        if (!isValidPhone(phoneInput && phoneInput.value)) {
            setFieldError(
                phoneInput,
                phoneError,
                "Укажите номер в формате +7 (XXX) XXX-XX-XX.",
                true
            );
            ok = false;
        }
        var privacy = form.querySelector('input[name="accept_privacy"]');
        if (!privacy || !privacy.checked) {
            if (privacyError) {
                privacyError.hidden = false;
            }
            if (consent) {
                consent.classList.add("is-invalid");
            }
            ok = false;
        }
        return ok;
    }

    form.addEventListener("submit", function (event) {
        if (!validateForm()) {
            event.preventDefault();
            var firstBad =
                form.querySelector(".is-invalid") ||
                (consent && consent.classList.contains("is-invalid") ? consent : null);
            if (firstBad && typeof firstBad.scrollIntoView === "function") {
                firstBad.scrollIntoView({ behavior: "smooth", block: "center" });
            }
        }
    });

    if (fioInput) {
        fioInput.addEventListener("input", function () {
            if (isValidFio(fioInput.value)) {
                setFieldError(fioInput, fioError, "", false);
            }
        });
    }
    if (phoneInput) {
        phoneInput.addEventListener("input", function () {
            if (isValidPhone(phoneInput.value)) {
                setFieldError(phoneInput, phoneError, "", false);
            }
        });
    }
    var privacyInput = form.querySelector('input[name="accept_privacy"]');
    if (privacyInput) {
        privacyInput.addEventListener("change", function () {
            if (privacyInput.checked) {
                if (privacyError) {
                    privacyError.hidden = true;
                }
                if (consent) {
                    consent.classList.remove("is-invalid");
                }
            }
        });
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
                fillIfEmpty(
                    telegramInput,
                    data.telegram ? "@" + data.telegram.replace(/^@/, "") : ""
                );
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
        timer = setTimeout(runLookup, 400);
    }

    if (phoneInput) {
        phoneInput.addEventListener("blur", scheduleLookup);
    }
    if (telegramInput) {
        telegramInput.addEventListener("blur", scheduleLookup);
    }
})();
