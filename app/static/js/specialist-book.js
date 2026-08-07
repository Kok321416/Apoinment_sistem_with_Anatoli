/**
 * Specialist manual booking wizard (cabinet).
 * POST /api/specialist/bookings/
 */
(function () {
    "use strict";

    function el(html) {
        var t = document.createElement("template");
        t.innerHTML = html.trim();
        return t.content.firstChild;
    }

    function qs(root, sel) {
        return root.querySelector(sel);
    }

    function csrfToken() {
        var m = document.querySelector('meta[name="csrf-token"]');
        if (m && m.content) return m.content;
        var page = document.querySelector("[data-csrf]");
        return page ? page.getAttribute("data-csrf") : "";
    }

    function openModal(opts) {
        opts = opts || {};
        var existing = document.getElementById("specialist-book-modal");
        if (existing) existing.remove();

        var modal = el(
            '<div class="sb-modal" id="specialist-book-modal" role="dialog" aria-modal="true" aria-labelledby="sb-title">' +
                '<div class="sb-modal__backdrop" data-sb-close></div>' +
                '<div class="sb-modal__panel">' +
                '<header class="sb-modal__head">' +
                '<h2 class="sb-modal__title" id="sb-title">Записать клиента</h2>' +
                '<button type="button" class="btn btn--ghost btn--sm" data-sb-close aria-label="Закрыть">Закрыть</button>' +
                "</header>" +
                '<p class="sb-modal__note">Вы вносите данные клиента как специалист. Согласие клиента на обработку ПДн оформляется вне этой формы (см. Политику конфиденциальности).</p>' +
                '<div class="sb-modal__steps" id="sb-steps" aria-label="Шаги"></div>' +
                '<div class="sb-modal__body" id="sb-body"></div>' +
                '<div class="sb-modal__status" id="sb-status" role="status" hidden></div>' +
                '<footer class="sb-modal__foot">' +
                '<button type="button" class="btn btn--ghost" data-sb-prev>Назад</button>' +
                '<button type="button" class="btn btn--primary" data-sb-next>Далее</button>' +
                "</footer>" +
                "</div></div>"
        );
        document.body.appendChild(modal);

        var state = {
            step: 0,
            calendars: [],
            services: [],
            slots: [],
            calendar_id: null,
            service_id: null,
            booking_date: "",
            booking_time: "",
            booking_end_time: "",
            client_name: "",
            client_phone: "",
            client_email: "",
            client_telegram: "",
            client_card_id: null,
            force_new_client: false,
            matches: [],
        };

        var steps = ["Клиент", "Календарь", "Услуга", "Дата и время", "Проверка"];

        function setStatus(msg, isError) {
            var box = qs(modal, "#sb-status");
            box.hidden = !msg;
            box.textContent = msg || "";
            box.classList.toggle("is-error", !!isError);
        }

        function renderSteps() {
            qs(modal, "#sb-steps").innerHTML = steps
                .map(function (label, i) {
                    var cls = "sb-step" + (i === state.step ? " is-active" : "") + (i < state.step ? " is-done" : "");
                    return '<span class="' + cls + '">' + (i + 1) + ". " + label + "</span>";
                })
                .join("");
        }

        function renderBody() {
            var body = qs(modal, "#sb-body");
            var nextBtn = qs(modal, "[data-sb-next]");
            var prevBtn = qs(modal, "[data-sb-prev]");
            prevBtn.hidden = state.step === 0;
            nextBtn.textContent = state.step === steps.length - 1 ? "Создать запись" : "Далее";

            if (state.step === 0) {
                body.innerHTML =
                    '<div class="form-field"><label class="form-field__label" for="sb-name">ФИО *</label>' +
                    '<input class="input" id="sb-name" required value="' +
                    (state.client_name || "") +
                    '"></div>' +
                    '<div class="app-form-grid">' +
                    '<div class="form-field"><label class="form-field__label" for="sb-phone">Телефон</label><input class="input" id="sb-phone" value="' +
                    (state.client_phone || "") +
                    '"></div>' +
                    '<div class="form-field"><label class="form-field__label" for="sb-email">Email</label><input class="input" id="sb-email" type="email" value="' +
                    (state.client_email || "") +
                    '"></div>' +
                    '<div class="form-field"><label class="form-field__label" for="sb-tg">Telegram</label><input class="input" id="sb-tg" placeholder="@username" value="' +
                    (state.client_telegram || "") +
                    '"></div></div>' +
                    (state.matches.length
                        ? '<div class="sb-matches"><p>Найдены похожие клиенты:</p><ul>' +
                          state.matches
                              .map(function (m) {
                                  return (
                                      '<li><button type="button" class="btn btn--secondary btn--sm" data-pick-card="' +
                                      m.id +
                                      '">' +
                                      m.name +
                                      (m.phone ? " · " + m.phone : "") +
                                      "</button></li>"
                                  );
                              })
                              .join("") +
                          '</ul><button type="button" class="btn btn--ghost btn--sm" data-force-new>Создать новую карточку</button></div>'
                        : "");
            } else if (state.step === 1) {
                body.innerHTML =
                    '<div class="sb-cards">' +
                    state.calendars
                        .map(function (c) {
                            return (
                                '<button type="button" class="sb-card' +
                                (String(state.calendar_id) === String(c.id) ? " is-selected" : "") +
                                (!c.is_active ? " is-disabled" : "") +
                                '" data-cal="' +
                                c.id +
                                '" ' +
                                (!c.is_active ? "disabled" : "") +
                                ">" +
                                "<strong>" +
                                c.name +
                                "</strong>" +
                                '<span class="badge badge--' +
                                (c.is_active ? "success" : "secondary") +
                                '">' +
                                (c.is_active ? "Активен" : "Выкл") +
                                "</span></button>"
                            );
                        })
                        .join("") +
                    "</div>";
            } else if (state.step === 2) {
                var list = state.services.filter(function (s) {
                    return !s.calendar_id || String(s.calendar_id) === String(state.calendar_id);
                });
                body.innerHTML = list.length
                    ? '<div class="sb-cards">' +
                      list
                          .map(function (s) {
                              return (
                                  '<button type="button" class="sb-card' +
                                  (String(state.service_id) === String(s.id) ? " is-selected" : "") +
                                  '" data-svc="' +
                                  s.id +
                                  '"><strong>' +
                                  s.name +
                                  "</strong><span>" +
                                  s.duration_minutes +
                                  " мин</span></button>"
                              );
                          })
                          .join("") +
                      "</div>"
                    : '<p class="text-muted">Нет активных услуг для этого календаря.</p>';
            } else if (state.step === 3) {
                body.innerHTML =
                    '<div class="form-field"><label class="form-field__label" for="sb-date">Дата</label>' +
                    '<input class="input" type="date" id="sb-date" value="' +
                    (state.booking_date || "") +
                    '"></div>' +
                    '<div id="sb-slots" class="sb-slots">' +
                    (state.slots.length
                        ? state.slots
                              .map(function (slot) {
                                  var start = slot.start || slot.booking_time || slot[0];
                                  var end = slot.end || slot.booking_end_time || slot[1];
                                  if (typeof slot === "string") {
                                      start = slot;
                                      end = "";
                                  }
                                  return (
                                      '<button type="button" class="sb-slot' +
                                      (state.booking_time === start ? " is-selected" : "") +
                                      '" data-start="' +
                                      start +
                                      '" data-end="' +
                                      end +
                                      '">' +
                                      start +
                                      (end ? "–" + end : "") +
                                      "</button>"
                                  );
                              })
                              .join("")
                        : '<p class="text-muted" id="sb-slots-empty">Выберите дату, чтобы загрузить слоты.</p>') +
                    "</div>";
            } else {
                body.innerHTML =
                    '<dl class="sb-summary">' +
                    "<div><dt>Клиент</dt><dd>" +
                    (state.client_name || "—") +
                    "</dd></div>" +
                    "<div><dt>Контакты</dt><dd>" +
                    [state.client_phone, state.client_email, state.client_telegram].filter(Boolean).join(" · ") +
                    "</dd></div>" +
                    "<div><dt>Дата и время</dt><dd>" +
                    state.booking_date +
                    " " +
                    state.booking_time +
                    (state.booking_end_time ? "–" + state.booking_end_time : "") +
                    "</dd></div>" +
                    "</dl>";
            }
        }

        async function loadCalendars() {
            setStatus("Загрузка…", false);
            var res = await fetch("/api/specialist/calendars/", { credentials: "same-origin" });
            var data = await res.json();
            state.calendars = data.calendars || [];
            setStatus("", false);
            renderBody();
        }

        async function loadServices() {
            setStatus("Загрузка услуг…", false);
            var res = await fetch(
                "/api/specialist/services/?calendar_id=" + encodeURIComponent(state.calendar_id),
                { credentials: "same-origin" }
            );
            var data = await res.json();
            state.services = data.services || [];
            setStatus("", false);
            renderBody();
        }

        async function loadSlots() {
            if (!state.booking_date || !state.calendar_id || !state.service_id) return;
            setStatus("Загрузка слотов…", false);
            var url =
                "/api/specialist/slots/?calendar_id=" +
                encodeURIComponent(state.calendar_id) +
                "&service_id=" +
                encodeURIComponent(state.service_id) +
                "&booking_date=" +
                encodeURIComponent(state.booking_date);
            var res = await fetch(url, { credentials: "same-origin" });
            var data = await res.json();
            var raw = data.available_slots || data.slots || [];
            state.slots = raw.map(function (s) {
                if (typeof s === "string") return { start: s, end: "" };
                return {
                    start: s.start_time || s.start || s.booking_time || s.time || "",
                    end: s.end_time || s.end || s.booking_end_time || "",
                };
            });
            setStatus(state.slots.length ? "" : "Нет свободных слотов на эту дату", !state.slots.length);
            renderBody();
        }

        function readStep0() {
            state.client_name = (qs(modal, "#sb-name") || {}).value || "";
            state.client_phone = (qs(modal, "#sb-phone") || {}).value || "";
            state.client_email = (qs(modal, "#sb-email") || {}).value || "";
            state.client_telegram = (qs(modal, "#sb-tg") || {}).value || "";
            if (!state.client_name.trim()) {
                setStatus("Укажите ФИО клиента", true);
                return false;
            }
            return true;
        }

        async function submit() {
            setStatus("Создание записи…", false);
            var payload = {
                csrf_token: csrfToken() || opts.csrf || "",
                client_name: state.client_name,
                client_phone: state.client_phone || null,
                client_email: state.client_email || null,
                client_telegram: state.client_telegram || null,
                calendar_id: state.calendar_id,
                service_id: state.service_id,
                booking_date: state.booking_date,
                booking_time: state.booking_time,
                booking_end_time: state.booking_end_time,
                client_card_id: state.client_card_id,
                force_new_client: state.force_new_client,
            };
            Object.keys(payload).forEach(function (k) {
                if (payload[k] === null || payload[k] === "") delete payload[k];
            });
            payload.csrf_token = csrfToken() || opts.csrf || "";
            payload.client_name = state.client_name;
            payload.calendar_id = state.calendar_id;
            payload.service_id = state.service_id;
            payload.booking_date = state.booking_date;
            payload.booking_time = state.booking_time;
            payload.booking_end_time = state.booking_end_time;
            if (state.client_phone) payload.client_phone = state.client_phone;
            if (state.client_email) payload.client_email = state.client_email;
            if (state.client_telegram) payload.client_telegram = state.client_telegram;
            if (state.client_card_id) payload.client_card_id = state.client_card_id;
            if (state.force_new_client) payload.force_new_client = true;

            var res = await fetch("/api/specialist/bookings/", {
                method: "POST",
                credentials: "same-origin",
                headers: { "Content-Type": "application/json", "X-CSRF-Token": payload.csrf_token },
                body: JSON.stringify(payload),
            });
            var data = await res.json().catch(function () {
                return {};
            });
            if (res.status === 409 && data.error === "found_matches") {
                state.matches = data.matches || [];
                state.step = 0;
                setStatus(data.message || "Найдены похожие клиенты", true);
                renderSteps();
                renderBody();
                return;
            }
            if (!res.ok || !data.ok) {
                setStatus(data.error || "Не удалось создать запись", true);
                return;
            }
            setStatus("Запись создана", false);
            if (typeof opts.onSuccess === "function") opts.onSuccess(data.booking);
            else window.location.href = "/booking/?success=" + encodeURIComponent("Запись создана");
            setTimeout(function () {
                modal.remove();
            }, 600);
        }

        modal.addEventListener("click", function (e) {
            var t = e.target;
            if (t.closest("[data-sb-close]")) {
                modal.remove();
                return;
            }
            var cal = t.closest("[data-cal]");
            if (cal) {
                state.calendar_id = parseInt(cal.getAttribute("data-cal"), 10);
                state.service_id = null;
                renderBody();
                return;
            }
            var svc = t.closest("[data-svc]");
            if (svc) {
                state.service_id = parseInt(svc.getAttribute("data-svc"), 10);
                renderBody();
                return;
            }
            var slot = t.closest("[data-start]");
            if (slot) {
                state.booking_time = slot.getAttribute("data-start");
                state.booking_end_time = slot.getAttribute("data-end") || "";
                renderBody();
                return;
            }
            var pick = t.closest("[data-pick-card]");
            if (pick) {
                state.client_card_id = parseInt(pick.getAttribute("data-pick-card"), 10);
                state.force_new_client = false;
                state.matches = [];
                setStatus("Выбрана существующая карточка", false);
                return;
            }
            if (t.closest("[data-force-new]")) {
                state.force_new_client = true;
                state.client_card_id = null;
                state.matches = [];
                setStatus("Будет создана новая карточка", false);
                renderBody();
            }
        });

        qs(modal, "[data-sb-prev]").addEventListener("click", function () {
            if (state.step > 0) {
                state.step -= 1;
                setStatus("", false);
                renderSteps();
                renderBody();
            }
        });

        qs(modal, "[data-sb-next]").addEventListener("click", async function () {
            setStatus("", false);
            if (state.step === 0) {
                if (!readStep0()) return;
                state.step = 1;
                renderSteps();
                await loadCalendars();
                return;
            }
            if (state.step === 1) {
                if (!state.calendar_id) {
                    setStatus("Выберите календарь", true);
                    return;
                }
                state.step = 2;
                renderSteps();
                await loadServices();
                return;
            }
            if (state.step === 2) {
                if (!state.service_id) {
                    setStatus("Выберите услугу", true);
                    return;
                }
                state.step = 3;
                renderSteps();
                renderBody();
                return;
            }
            if (state.step === 3) {
                var dateInput = qs(modal, "#sb-date");
                if (dateInput) state.booking_date = dateInput.value;
                if (!state.booking_date) {
                    setStatus("Выберите дату", true);
                    return;
                }
                if (!state.booking_time || !state.booking_end_time) {
                    setStatus("Выберите свободное время", true);
                    return;
                }
                state.step = 4;
                renderSteps();
                renderBody();
                return;
            }
            await submit();
        });

        modal.addEventListener("change", function (e) {
            if (e.target && e.target.id === "sb-date") {
                state.booking_date = e.target.value;
                state.booking_time = "";
                state.booking_end_time = "";
                loadSlots();
            }
        });

        renderSteps();
        renderBody();
    }

    document.addEventListener("click", function (e) {
        var btn = e.target.closest("[data-specialist-book]");
        if (!btn) return;
        e.preventDefault();
        openModal({
            csrf: btn.getAttribute("data-csrf") || csrfToken(),
        });
    });

    window.AYCSpecialistBook = { open: openModal };
})();
