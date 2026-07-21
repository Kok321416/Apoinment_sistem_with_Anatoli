(function () {
    "use strict";

    function extractDigits(text) {
        return String(text || "").replace(/\D/g, "").slice(0, 6);
    }

    function initVerificationCode(root) {
        var digits = Array.prototype.slice.call(root.querySelectorAll(".verification-code__digit"));
        var hidden = root.querySelector('input[type="hidden"][data-verification-value]');
        if (!digits.length || !hidden) {
            return;
        }

        function syncHidden() {
            hidden.value = digits.map(function (input) {
                return input.value;
            }).join("");
        }

        function focusDigit(index) {
            var target = digits[Math.max(0, Math.min(index, digits.length - 1))];
            if (target) {
                target.focus();
                target.select();
            }
        }

        function fillFromString(str) {
            var nums = extractDigits(str);
            digits.forEach(function (input, index) {
                input.value = nums.charAt(index) || "";
            });
            syncHidden();
            focusDigit(nums.length >= 6 ? 5 : nums.length);
        }

        function handlePaste(event) {
            var text = "";
            if (event.clipboardData) {
                text = event.clipboardData.getData("text");
            }
            if (!text) {
                return;
            }
            event.preventDefault();
            fillFromString(text);
        }

        root.addEventListener("paste", handlePaste);
        digits.forEach(function (input, index) {
            input.addEventListener("paste", handlePaste);

            input.addEventListener("input", function () {
                var value = extractDigits(input.value);
                if (value.length > 1) {
                    fillFromString(value);
                    return;
                }
                input.value = value;
                syncHidden();
                if (value && index < digits.length - 1) {
                    focusDigit(index + 1);
                }
            });

            input.addEventListener("keydown", function (event) {
                if (event.key === "Backspace") {
                    if (!input.value && index > 0) {
                        event.preventDefault();
                        digits[index - 1].value = "";
                        syncHidden();
                        focusDigit(index - 1);
                    }
                    return;
                }
                if (event.key === "ArrowLeft" && index > 0) {
                    event.preventDefault();
                    focusDigit(index - 1);
                }
                if (event.key === "ArrowRight" && index < digits.length - 1) {
                    event.preventDefault();
                    focusDigit(index + 1);
                }
            });

            input.addEventListener("focus", function () {
                input.select();
            });
        });

        var form = root.closest("form");
        if (form) {
            form.addEventListener("submit", function (event) {
                syncHidden();
                if (hidden.value.length !== 6) {
                    event.preventDefault();
                    focusDigit(hidden.value.length);
                }
            });
        }
    }

    function initSingleCodeInput(input) {
        function normalize() {
            input.value = extractDigits(input.value);
        }

        input.addEventListener("input", normalize);
        input.addEventListener("paste", function (event) {
            var text = event.clipboardData ? event.clipboardData.getData("text") : "";
            if (!text) {
                return;
            }
            event.preventDefault();
            input.value = extractDigits(text);
        });
    }

    function boot() {
        document.querySelectorAll("[data-verification-code]").forEach(initVerificationCode);
        document.querySelectorAll(".input--code:not([data-verification-code] *)").forEach(function (input) {
            if (!input.closest("[data-verification-code]")) {
                initSingleCodeInput(input);
            }
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot);
    } else {
        boot();
    }
})();
