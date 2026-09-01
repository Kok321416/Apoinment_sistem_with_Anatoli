(function () {
    "use strict";

    var form = document.querySelector(".diag-form");
    if (!form) {
        return;
    }

    var submitBtn = form.querySelector('button[type="submit"]');
    var overlay = document.getElementById("diagSubmitOverlay");
    var submitting = false;

    form.addEventListener("submit", function (event) {
        if (submitting) {
            event.preventDefault();
            return;
        }
        if (!form.checkValidity()) {
            return;
        }
        submitting = true;
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.setAttribute("aria-busy", "true");
            submitBtn.textContent = "Считаем результат…";
        }
        if (overlay) {
            overlay.hidden = false;
            overlay.setAttribute("aria-hidden", "false");
        }
    });
})();
