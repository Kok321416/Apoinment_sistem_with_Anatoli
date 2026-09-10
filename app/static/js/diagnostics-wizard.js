(function () {
    "use strict";

    var root = document.getElementById("diagWizard");
    if (!root) {
        return;
    }

    var allSlides = Array.prototype.slice.call(root.querySelectorAll(".diag-wizard__slide"));
    if (!allSlides.length) {
        return;
    }

    var form = root.querySelector("form") || document.getElementById("diagTakeForm");
    var idx = 0;
    var qNum = document.getElementById("diagQNum");
    var qTotal = document.getElementById("diagQTotal");
    var fill = document.getElementById("diagProgressFill");
    var bar = document.getElementById("diagProgressBar");
    var prevBtn = document.getElementById("diagPrevBtn");
    var nextBtn = document.getElementById("diagNextBtn");
    var submitBtn = document.getElementById("diagSubmitBtn");

    function formValue(name) {
        if (!form || !name) {
            return "";
        }
        var checked = form.querySelector('input[name="' + name + '"]:checked');
        if (checked) {
            return String(checked.value);
        }
        var el = form.querySelector('[name="' + name + '"]');
        return el ? String(el.value || "") : "";
    }

    function slideVisible(slide) {
        var item = slide.getAttribute("data-show-if-item") || "";
        var raw = slide.getAttribute("data-show-if-values") || "";
        if (!item) {
            return true;
        }
        var allowed = raw.split(",").map(function (v) { return v.trim(); }).filter(Boolean);
        return allowed.indexOf(formValue(item)) !== -1;
    }

    function visibleSlides() {
        return allSlides.filter(slideVisible);
    }

    function currentSlide() {
        var vis = visibleSlides();
        if (idx >= vis.length) {
            idx = Math.max(0, vis.length - 1);
        }
        return vis[idx];
    }

    function answered(slide) {
        if (!slide) {
            return false;
        }
        var requiredRadios = slide.querySelectorAll('input[type="radio"][data-step-required]');
        var names = {};
        requiredRadios.forEach(function (radio) {
            names[radio.name] = names[radio.name] || false;
            if (radio.checked) {
                names[radio.name] = true;
            }
        });
        var radioOk = true;
        Object.keys(names).forEach(function (name) {
            if (!names[name]) {
                radioOk = false;
            }
        });
        var ranges = slide.querySelectorAll('input[type="range"][data-step-required]');
        return radioOk && ranges.length >= 0;
    }

    function syncOtherFields() {
        root.querySelectorAll(".diag-other").forEach(function (box) {
            var name = box.getAttribute("data-other-for");
            var values = (box.getAttribute("data-other-values") || "").split(",").map(function (v) {
                return v.trim();
            }).filter(Boolean);
            var show = values.indexOf(formValue(name)) !== -1;
            box.hidden = !show;
            if (!show) {
                var ta = box.querySelector("textarea, input");
                if (ta) {
                    ta.value = "";
                }
            }
        });
    }

    function relaxHiddenRequired() {
        allSlides.forEach(function (slide) {
            var on = slideVisible(slide) && slide.classList.contains("is-active");
            slide.querySelectorAll("input[required], textarea[required]").forEach(function (input) {
                if (!slideVisible(slide)) {
                    input.removeAttribute("required");
                    if (input.type === "radio" && input.checked) {
                        input.checked = false;
                    }
                    if (!slideVisible(slide) && input.name && input.name.indexOf("_note") !== -1) {
                        input.value = "";
                    }
                } else if (input.type === "range" || input.type === "radio") {
                    if (input.hasAttribute("data-step-required") || input.type === "range") {
                        input.setAttribute("required", "required");
                    }
                }
            });
            void on;
        });
        allSlides.forEach(function (slide) {
            if (!slideVisible(slide)) {
                slide.querySelectorAll("input[name], textarea[name]").forEach(function (input) {
                    if (input.type === "radio") {
                        input.checked = false;
                        input.removeAttribute("required");
                    } else if (input.name && input.name.indexOf("_note") !== -1) {
                        input.value = "";
                    } else if (input.type !== "range") {
                        input.removeAttribute("required");
                    }
                });
            }
        });
    }

    function updateUI() {
        var vis = visibleSlides();
        if (!vis.length) {
            return;
        }
        if (idx >= vis.length) {
            idx = vis.length - 1;
        }
        allSlides.forEach(function (slide) {
            slide.classList.remove("is-active");
            slide.hidden = true;
        });
        vis.forEach(function (slide, i) {
            var active = i === idx;
            slide.classList.toggle("is-active", active);
            slide.hidden = !active;
        });
        if (qNum) {
            qNum.textContent = String(idx + 1);
        }
        if (qTotal) {
            qTotal.textContent = String(vis.length);
        }
        var pct = Math.round(((idx + 1) / vis.length) * 100);
        if (fill) {
            fill.style.width = pct + "%";
        }
        if (bar) {
            bar.setAttribute("aria-valuenow", String(pct));
        }
        if (prevBtn) {
            prevBtn.disabled = idx === 0;
        }
        var last = idx === vis.length - 1;
        if (nextBtn) {
            nextBtn.hidden = last;
        }
        if (submitBtn) {
            submitBtn.hidden = !last;
        }
        vis.forEach(function (slide, i) {
            var n = slide.querySelector(".diag-item__n");
            if (n) {
                n.textContent = (i + 1) + ". ";
            }
        });
        syncOtherFields();
        relaxHiddenRequired();
    }

    function go(delta) {
        var vis = visibleSlides();
        var next = idx + delta;
        if (next < 0 || next >= vis.length) {
            return;
        }
        if (delta > 0 && !answered(currentSlide())) {
            currentSlide().classList.add("diag-wizard__slide--error");
            return;
        }
        currentSlide().classList.remove("diag-wizard__slide--error");
        idx = next;
        updateUI();
        var focusTarget = currentSlide().querySelector(".diag-opt input, input[type='range']");
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

    allSlides.forEach(function (slide) {
        slide.querySelectorAll('input[type="radio"]').forEach(function (radio) {
            radio.addEventListener("change", function () {
                slide.classList.remove("diag-wizard__slide--error");
                var visBefore = visibleSlides().length;
                syncOtherFields();
                var visAfter = visibleSlides().length;
                if (visAfter !== visBefore && idx >= visAfter) {
                    idx = Math.max(0, visAfter - 1);
                }
                updateUI();
            });
        });
        slide.querySelectorAll('input[type="range"]').forEach(function (range) {
            var valueEl = range.parentNode.querySelector(".diag-slider__value");
            function sync() {
                if (valueEl) {
                    valueEl.textContent = range.value;
                }
            }
            range.addEventListener("input", sync);
            range.addEventListener("change", sync);
            sync();
        });
    });

    if (form) {
        form.addEventListener("submit", function () {
            relaxHiddenRequired();
        });
    }

    updateUI();
})();
