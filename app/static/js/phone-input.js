/**
 * Unified RU phone mask: +7 (___) ___-__-__
 * Bind via data-phone-mask on inputs, or AycPhone.bind(el).
 */
(function (global) {
    "use strict";

    function digitsOnly(value) {
        return String(value || "").replace(/\D/g, "");
    }

    function toNationalDigits(raw) {
        var d = digitsOnly(raw);
        if (!d) return "";
        if (d.charAt(0) === "8") d = "7" + d.slice(1);
        if (d.charAt(0) === "9") d = "7" + d;
        if (d.charAt(0) !== "7") d = "7" + d;
        return d.slice(0, 11);
    }

    function format(raw) {
        var d = toNationalDigits(raw);
        var rest = d.slice(1);
        var out = "+7";
        if (!rest.length) return out;
        out += " (" + rest.slice(0, 3);
        if (rest.length < 3) return out;
        out += ") " + rest.slice(3, 6);
        if (rest.length < 6) return out;
        out += "-" + rest.slice(6, 8);
        if (rest.length < 8) return out;
        out += "-" + rest.slice(8, 10);
        return out;
    }

    function isComplete(value) {
        var d = toNationalDigits(value);
        return d.length === 11 && d.charAt(1) === "9";
    }

    function toE164(value) {
        var d = toNationalDigits(value);
        if (d.length === 11 && d.charAt(1) === "9") return "+" + d;
        return "";
    }

    function bind(input, opts) {
        opts = opts || {};
        if (!input || input._aycPhoneBound) return input;
        input._aycPhoneBound = true;
        input.setAttribute("type", "tel");
        input.setAttribute("inputmode", "numeric");
        input.setAttribute("autocomplete", opts.autocomplete || "tel");
        if (!input.getAttribute("placeholder")) {
            input.setAttribute("placeholder", "+7 (___) ___-__-__");
        }

        function applyFrom(raw) {
            var next = format(raw);
            if (input.value !== next) input.value = next;
        }

        if (digitsOnly(input.value).length > 1) {
            applyFrom(input.value);
        } else if (opts.showEmptyMask) {
            input.value = "+7 (";
        }

        input.addEventListener("focus", function () {
            if (digitsOnly(input.value).length <= 1) input.value = "+7 (";
        });

        input.addEventListener("blur", function () {
            if (!isComplete(input.value) && digitsOnly(input.value).length <= 1) {
                if (!input.required && input.getAttribute("data-phone-required") !== "1") {
                    input.value = "";
                }
            }
        });

        input.addEventListener("input", function () {
            applyFrom(input.value);
        });

        input.addEventListener("paste", function (event) {
            event.preventDefault();
            var text =
                (event.clipboardData || global.clipboardData).getData("text") || "";
            applyFrom(text);
        });

        input.addEventListener("keydown", function (event) {
            if (event.ctrlKey || event.metaKey || event.altKey) return;
            var nav = {
                Backspace: 1,
                Delete: 1,
                Tab: 1,
                Escape: 1,
                Enter: 1,
                ArrowLeft: 1,
                ArrowRight: 1,
                ArrowUp: 1,
                ArrowDown: 1,
                Home: 1,
                End: 1,
            };
            if (nav[event.key]) return;
            if (/^\d$/.test(event.key)) return;
            event.preventDefault();
        });

        return input;
    }

    function bindAll(root) {
        root = root || document;
        var nodes = root.querySelectorAll("input[data-phone-mask]");
        for (var i = 0; i < nodes.length; i++) {
            bind(nodes[i], {
                showEmptyMask: nodes[i].getAttribute("data-phone-lazy") === "0",
            });
        }
    }

    function prepareForSubmit(form) {
        var inputs = form.querySelectorAll("input[data-phone-mask]");
        for (var i = 0; i < inputs.length; i++) {
            var el = inputs[i];
            var required = el.required || el.getAttribute("data-phone-required") === "1";
            var digits = toNationalDigits(el.value);
            if (!required && digits.length <= 1) {
                el.value = "";
                continue;
            }
            if (required || digits.length > 1) {
                if (!isComplete(el.value)) return el;
                el.value = toE164(el.value);
            }
        }
        return null;
    }

    function onReady(fn) {
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", fn);
        } else {
            fn();
        }
    }

    onReady(function () {
        bindAll(document);
        document.addEventListener(
            "submit",
            function (event) {
                var form = event.target;
                if (!form || !form.querySelector || !form.querySelector("input[data-phone-mask]")) {
                    return;
                }
                var bad = prepareForSubmit(form);
                if (bad) {
                    event.preventDefault();
                    bad.focus();
                    global.alert("Укажите полный номер телефона в формате +7 (___) ___-__-__");
                }
            },
            true
        );
    });

    global.AycPhone = {
        bind: bind,
        bindAll: bindAll,
        format: format,
        isComplete: isComplete,
        toE164: toE164,
        prepareForSubmit: prepareForSubmit,
        toNationalDigits: toNationalDigits,
    };
})(window);
