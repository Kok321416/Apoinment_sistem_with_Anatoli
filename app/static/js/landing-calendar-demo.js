(function () {
  function bindToggle(root, selector) {
    if (!root) return;
    root.addEventListener("click", function (event) {
      var target = event.target.closest(selector);
      if (!target || !root.contains(target)) return;
      root.querySelectorAll(selector + ".is-active").forEach(function (el) {
        if (el !== target) el.classList.remove("is-active");
      });
      target.classList.toggle("is-active");
    });
  }

  function bindWindows(windows) {
    if (!windows) return;
    bindToggle(windows, ".lp-window");
    windows.addEventListener("pointerover", function (event) {
      var col = event.target.closest(".lp-windows__col");
      if (!col || !windows.contains(col)) return;
      windows.querySelectorAll(".lp-windows__col.is-hot").forEach(function (el) {
        if (el !== col) el.classList.remove("is-hot");
      });
      col.classList.add("is-hot");
    });
    windows.addEventListener("pointerout", function (event) {
      var col = event.target.closest(".lp-windows__col");
      if (!col || !windows.contains(col)) return;
      if (col.contains(event.relatedTarget)) return;
      col.classList.remove("is-hot");
    });
  }

  document.querySelectorAll(".lp-windows-card").forEach(bindWindows);
  bindToggle(document.querySelector(".hero__preview"), ".lp-cal-slot");
  document.querySelectorAll("#calendar-preview .lp-week, #calendar-preview .lp-month").forEach(function (root) {
    bindToggle(root, ".lp-cal-slot");
  });
})();
