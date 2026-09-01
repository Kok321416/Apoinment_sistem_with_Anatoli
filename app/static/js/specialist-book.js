/**
 * Specialist manual booking wizard (cabinet + TG webview same JS).
 * POST /api/specialist/bookings/
 * GET  /api/specialist/clients/?q=
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

    function esc(s) {
        return String(s == null ? "" : s)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function csrfToken() {
        var m = document.querySelector('meta[name="csrf-token"]');
        if (m && m.content) return m.content;
        var page = document.querySelector("[data-csrf]");
        return page ? page.getAttribute("data-csrf") : "";
    }

    function contactLine(m) {
        return [m.phone, m.email, m.telegram].filter(Boolean).join(" · ");
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
                '<p class="sb-modal__note">Найдите клиента по имени или Telegram-нику. Если карточки нет - заполните данные вручную.</p>' +
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
            slots_fetched: false,
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
            search_q: "",
            search_results: [],
            search_loading: false,
            selected_card: null,
        };

        if (opts && opts.client && opts.client.id) {
            state.client_card_id = opts.client.id;
            state.selected_card = opts.client;
            state.client_name = opts.client.name || "";
            state.client_phone = opts.client.phone || "";
            state.client_email = opts.client.email || "";
            state.client_telegram = opts.client.telegram || "";
            state.step = 1;
        }

        var steps = ["Клиент", "Календарь", "Услуга", "Дата и время", "Проверка"];
        var searchTimer = null;

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

        function applyCard(card) {
            state.client_card_id = card.id;
            state.selected_card = card;
            state.force_new_client = false;
            state.client_name = card.name || "";
            state.client_phone = card.phone || "";
            state.client_email = card.email || "";
            state.client_telegram = card.telegram || "";
            state.matches = [];
            state.search_results = [];
        }

        function clearSelectedCard() {
            state.client_card_id = null;
            state.selected_card = null;
            state.force_new_client = false;
        }

        function renderClientResults(list, emptyText) {
            if (!list || !list.length) {
                return emptyText ? '<p class="sb-search__empty text-muted">' + esc(emptyText) + "</p>" : "";
            }
            return (
                '<ul class="sb-search__list">' +
                list
                    .map(function (m) {
                        var selected = state.client_card_id === m.id;
                        return (
                            '<li><button type="button" class="sb-card sb-card--client' +
                            (selected ? " is-selected" : "") +
                            '" data-pick-card="' +
                            m.id +
                            '">' +
                            "<div><strong>" +
                            esc(m.name) +
                            "</strong>" +
                            (contactLine(m)
                                ? '<span class="sb-card__meta">' + esc(contactLine(m)) + "</span>"
                                : "") +
                            "</div>" +
                            '<span class="sb-card__action">' +
                            (selected ? "Выбрана" : "Выбрать") +
                            "</span></button></li>"
                        );
                    })
                    .join("") +
                "</ul>"
            );
        }

        function renderBody() {
            var body = qs(modal, "#sb-body");
            var nextBtn = qs(modal, "[data-sb-next]");
            var prevBtn = qs(modal, "[data-sb-prev]");
            prevBtn.hidden = state.step === 0;
            nextBtn.hidden = false;
            nextBtn.disabled = false;
            nextBtn.textContent = state.step === steps.length - 1 ? "Записать" : "Далее";

            if (state.step === 0) {
                var selectedBlock = state.selected_card
                    ? '<div class="sb-selected" role="status">' +
                      "<div><strong>Выбрана карточка:</strong> " +
                      esc(state.selected_card.name) +
                      (contactLine(state.selected_card)
                          ? '<span class="sb-card__meta">' + esc(contactLine(state.selected_card)) + "</span>"
                          : "") +
                      '</div><button type="button" class="btn btn--ghost btn--sm" data-clear-card>Сменить</button></div>'
                    : "";

                var resultsBlock = "";
                if (state.search_loading) {
                    resultsBlock = '<p class="text-muted">Ищем…</p>';
                } else if (state.search_q.trim().length >= 1) {
                    resultsBlock = renderClientResults(
                        state.search_results,
                        "Никого не нашли. Заполните поля ниже для новой карточки."
                    );
                } else if (state.matches.length) {
                    resultsBlock =
                        '<p class="sb-search__hint">Найдены похожие клиенты:</p>' +
                        renderClientResults(state.matches) +
                        '<button type="button" class="btn btn--ghost btn--sm" data-force-new>Создать новую карточку</button>';
                }

                var phoneLocked =
                    !!(
                        state.selected_card &&
                        state.client_phone &&
                        (!window.AycPhone || AycPhone.isComplete(state.client_phone))
                    );

                body.innerHTML =
                    '<div class="form-field"><label class="form-field__label" for="sb-search">Поиск по имени или Telegram</label>' +
                    '<input class="input" id="sb-search" type="search" autocomplete="off" placeholder="Начните вводить имя или @ник" value="' +
                    esc(state.search_q) +
                    '"></div>' +
                    selectedBlock +
                    '<div class="sb-search" id="sb-search-results">' +
                    resultsBlock +
                    "</div>" +
                    '<div class="sb-manual' +
                    (state.selected_card ? " is-locked" : "") +
                    '">' +
                    '<p class="sb-manual__title">' +
                    (state.selected_card ? "Данные из карточки" : "Или новый клиент") +
                    "</p>" +
                    '<div class="form-field"><label class="form-field__label" for="sb-name">ФИО *</label>' +
                    '<input class="input" id="sb-name" required ' +
                    (state.selected_card ? "readonly " : "") +
                    'value="' +
                    esc(state.client_name) +
                    '"></div>' +
                    '<div class="app-form-grid">' +
                    '<div class="form-field"><label class="form-field__label" for="sb-phone">Телефон *</label><input class="input" id="sb-phone" type="tel" data-phone-mask data-phone-required="1" required inputmode="numeric" autocomplete="tel" placeholder="+7 (___) ___-__-__" ' +
                    (phoneLocked ? "readonly " : "") +
                    'value="' +
                    esc(state.client_phone) +
                    '"></div>' +
                    '<div class="form-field"><label class="form-field__label" for="sb-email">Email</label><input class="input" id="sb-email" type="email" ' +
                    (state.selected_card ? "readonly " : "") +
                    'value="' +
                    esc(state.client_email) +
                    '"></div>' +
                    '<div class="form-field"><label class="form-field__label" for="sb-tg">Telegram</label><input class="input" id="sb-tg" placeholder="@username" ' +
                    (state.selected_card ? "readonly " : "") +
                    'value="' +
                    esc(state.client_telegram) +
                    '"></div></div></div>';

                var phoneInput = qs(modal, "#sb-phone");
                if (phoneInput && window.AycPhone) {
                    phoneInput._aycPhoneBound = false;
                    AycPhone.bind(phoneInput, { showEmptyMask: true });
                }

                var searchInput = qs(modal, "#sb-search");
                if (searchInput && !state.selected_card) {
                    searchInput.focus();
                    if (typeof searchInput.setSelectionRange === "function") {
                        var len = searchInput.value.length;
                        searchInput.setSelectionRange(len, len);
                    }
                }
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
                                esc(c.name) +
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
                                  esc(s.name) +
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
                    esc(state.booking_date) +
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
                                      esc(start) +
                                      '" data-end="' +
                                      esc(end) +
                                      '">' +
                                      esc(start) +
                                      (end ? "–" + esc(end) : "") +
                                      "</button>"
                                  );
                              })
                              .join("")
                        : state.slots_fetched && state.booking_date
                          ? '<p class="slots-empty-message" role="alert">Нет свободных слотов на эту дату</p>'
                          : '<p class="text-muted" id="sb-slots-empty">Выберите дату, чтобы загрузить слоты.</p>') +
                    "</div>";
            } else {
                body.innerHTML =
                    '<dl class="sb-summary">' +
                    "<div><dt>Клиент</dt><dd>" +
                    esc(state.client_name || "—") +
                    (state.client_card_id ? ' <span class="text-muted">(карточка #' + state.client_card_id + ")</span>" : "") +
                    "</dd></div>" +
                    "<div><dt>Контакты</dt><dd>" +
                    esc([state.client_phone, state.client_email, state.client_telegram].filter(Boolean).join(" · ") || "—") +
                    "</dd></div>" +
                    "<div><dt>Дата и время</dt><dd>" +
                    esc(state.booking_date) +
                    " " +
                    esc(state.booking_time) +
                    (state.booking_end_time ? "–" + esc(state.booking_end_time) : "") +
                    "</dd></div>" +
                    "</dl>";
            }
        }

        async function searchClients(q) {
            state.search_q = q;
            if (!q.trim()) {
                state.search_results = [];
                state.search_loading = false;
                renderBody();
                return;
            }
            state.search_loading = true;
            renderBody();
            try {
                var res = await fetch("/api/specialist/clients/?q=" + encodeURIComponent(q.trim()), {
                    credentials: "same-origin",
                });
                var data = await res.json();
                if (state.search_q.trim() !== q.trim()) return;
                state.search_results = data.clients || [];
            } catch (e) {
                state.search_results = [];
            }
            state.search_loading = false;
            renderBody();
        }

        function scheduleSearch(q) {
            if (searchTimer) clearTimeout(searchTimer);
            searchTimer = setTimeout(function () {
                searchClients(q);
            }, 250);
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
            state.slots_fetched = false;
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
            state.slots_fetched = true;
            setStatus("", false);
            renderBody();
        }

        function readStep0() {
            var phoneEl = qs(modal, "#sb-phone");
            if (!state.selected_card) {
                state.client_name = (qs(modal, "#sb-name") || {}).value || "";
                state.client_phone = (phoneEl || {}).value || "";
                state.client_email = (qs(modal, "#sb-email") || {}).value || "";
                state.client_telegram = (qs(modal, "#sb-tg") || {}).value || "";
            } else if (phoneEl && !phoneEl.readOnly) {
                state.client_phone = phoneEl.value || "";
            }
            if (!state.client_name.trim()) {
                setStatus("Укажите ФИО или выберите карточку из поиска", true);
                return false;
            }
            var phoneOk = window.AycPhone
                ? AycPhone.isComplete(state.client_phone)
                : /\+?7\d{10}/.test(String(state.client_phone || "").replace(/\D/g, "").replace(/^8/, "7"));
            if (!phoneOk) {
                setStatus("Укажите полный номер телефона в формате +7 (___) ___-__-__", true);
                if (phoneEl) phoneEl.focus();
                return false;
            }
            if (window.AycPhone) {
                state.client_phone = AycPhone.toE164(state.client_phone) || state.client_phone;
            }
            return true;
        }

        async function submit() {
            setStatus("Создание записи…", false);
            var payload = {
                csrf_token: csrfToken() || opts.csrf || "",
                client_name: state.client_name,
                calendar_id: state.calendar_id,
                service_id: state.service_id,
                booking_date: state.booking_date,
                booking_time: state.booking_time,
                booking_end_time: state.booking_end_time,
                client_phone: state.client_phone || "",
            };
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
                setStatus(data.message || "Найдены похожие клиенты. Выберите карточку.", true);
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

        function findCardById(id) {
            var pools = [state.search_results, state.matches];
            for (var i = 0; i < pools.length; i++) {
                for (var j = 0; j < pools[i].length; j++) {
                    if (pools[i][j].id === id) return pools[i][j];
                }
            }
            if (state.selected_card && state.selected_card.id === id) return state.selected_card;
            return null;
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
                var cid = parseInt(pick.getAttribute("data-pick-card"), 10);
                var card = findCardById(cid);
                if (!card) {
                    card = {
                        id: cid,
                        name: state.client_name || "Клиент #" + cid,
                        phone: state.client_phone || "",
                        email: state.client_email || "",
                        telegram: state.client_telegram || "",
                    };
                }
                applyCard(card);
                setStatus("Карточка выбрана. Нажмите «Далее».", false);
                renderBody();
                return;
            }
            if (t.closest("[data-clear-card]")) {
                clearSelectedCard();
                setStatus("", false);
                renderBody();
                return;
            }
            if (t.closest("[data-force-new]")) {
                state.force_new_client = true;
                clearSelectedCard();
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

        modal.addEventListener("input", function (e) {
            if (e.target && e.target.id === "sb-search") {
                if (state.selected_card) return;
                scheduleSearch(e.target.value || "");
            }
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
        var opts = {
            csrf: btn.getAttribute("data-csrf") || csrfToken(),
        };
        var cid = btn.getAttribute("data-client-id");
        if (cid) {
            opts.client = {
                id: Number(cid),
                name: btn.getAttribute("data-client-name") || "",
                phone: btn.getAttribute("data-client-phone") || "",
                email: btn.getAttribute("data-client-email") || "",
                telegram: btn.getAttribute("data-client-telegram") || "",
            };
        }
        openModal(opts);
    });

    window.AYCSpecialistBook = { open: openModal };
})();
