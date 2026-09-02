(function () {
    "use strict";

    var root = document.getElementById("diagWizard");
    if (!root) {
        return;
    }

    var slides = Array.prototype.slice.call(root.querySelectorAll(".diag-wizard__slide"));
    var total = slides.length;
    if (!total) {
        return;
    }

    var idx = 0;
    var qNum = document.getElementById("diagQNum");
    var fill = document.getElementById("diagProgressFill");
    var bar = document.getElementById("diagProgressBar");
    var prevBtn = document.getElementById("diagPrevBtn");
    var nextBtn = document.getElementById("diagNextBtn");
    var submitBtn = document.getElementById("diagSubmitBtn");

    function currentSlide() {
        return slides[idx];
    }

    function answered(slide) {
        var radios = slide.querySelectorAll('input[type="radio"]');
        for (var i = 0; i < radios.length; i++) {
            if (radios[i].checked) {
                return true;
            }
        }
        return false;
    }

    function updateUI() {
        slides.forEach(function (slide, i) {
            var active = i === idx;
            slide.classList.toggle("is-active", active);
            slide.hidden = !active;
        });
        if (qNum) {
            qNum.textContent = String(idx + 1);
        }
        var pct = Math.round(((idx + 1) / total) * 100);
        if (fill) {
            fill.style.width = pct + "%";
        }
        if (bar) {
            bar.setAttribute("aria-valuenow", String(pct));
        }
        if (prevBtn) {
            prevBtn.disabled = idx === 0;
        }
        var last = idx === total - 1;
        if (nextBtn) {
            nextBtn.hidden = last;
        }
        if (submitBtn) {
            submitBtn.hidden = !last;
        }
    }

    function go(delta) {
        var next = idx + delta;
        if (next < 0 || next >= total) {
            return;
        }
        if (delta > 0 && !answered(currentSlide())) {
            currentSlide().classList.add("diag-wizard__slide--error");
            return;
        }
        currentSlide().classList.remove("diag-wizard__slide--error");
        idx = next;
        updateUI();
        var focusTarget = currentSlide().querySelector(".diag-opt input");
        if (focusTarget) {
            focusTarget.focus();
        }
    }

    if (prevBtn) {
        prevBtn.addEventListener("click", function () {
            go(-1);
        });
    }
    if (nextBtn) {
        nextBtn.addEventListener("click", function () {
            go(1);
        });
    }

    slides.forEach(function (slide) {
        slide.querySelectorAll('input[type="radio"]').forEach(function (radio) {
            radio.addEventListener("change", function () {
                slide.classList.remove("diag-wizard__slide--error");
            });
        });
    });

    updateUI();
})();
