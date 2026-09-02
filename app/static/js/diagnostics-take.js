(function () {
    "use strict";

    var form = document.querySelector(".diag-form");
    if (!form) {
        return;
    }

    var submitBtn = form.querySelector('button[type="submit"]');
    var overlay = document.getElementById("diagSubmitOverlay");
    var submitting = false;

    function slideAnswered(slide) {
        var radios = slide.querySelectorAll('input[type="radio"]');
        for (var i = 0; i < radios.length; i++) {
            if (radios[i].checked) {
                return true;
            }
        }
        return false;
    }

    function allSlidesAnswered() {
        var slides = form.querySelectorAll(".diag-wizard__slide");
        for (var i = 0; i < slides.length; i++) {
            if (!slideAnswered(slides[i])) {
                slides[i].classList.add("diag-wizard__slide--error");
                return false;
            }
        }
        return true;
    }

    function relaxHiddenRequired() {
        form.querySelectorAll(".diag-wizard__slide[hidden] input[required]").forEach(function (input) {
            input.removeAttribute("required");
        });
    }

    form.addEventListener("submit", function (event) {
        if (submitting) {
            event.preventDefault();
            return;
        }
        relaxHiddenRequired();
        if (!allSlidesAnswered()) {
            event.preventDefault();
            var firstBad = form.querySelector(".diag-wizard__slide--error");
            if (firstBad && typeof firstBad.scrollIntoView === "function") {
                firstBad.scrollIntoView({ behavior: "smooth", block: "center" });
            }
            return;
        }
        if (!form.checkValidity()) {
            event.preventDefault();
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
