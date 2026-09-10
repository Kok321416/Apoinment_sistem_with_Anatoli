/**
 * Specialist calendar event (мероприятие) wizard.
 * POST /api/specialist/events/
 */
(function () {
    "use strict";

    function el(html) {
        var t = document.createElement("template");
        t.innerHTML = html.trim();
        return t.content.firstChild;
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

    function openModal() {
        var existing = document.getElementById("specialist-event-modal");
        if (existing) existing.remove();

        var modal = el(
            '<div class="sb-modal" id="specialist-event-modal" role="dialog" aria-modal="true" aria-labelledby="se-title">' +
                '<div class="sb-modal__backdrop" data-se-close></div>' +
                '<div class="sb-modal__panel">' +
                '<header class="sb-modal__head">' +
                '<h2 class="sb-modal__title" id="se-title">Добавить мероприятие</h2>' +
                '<button type="button" class="btn btn--ghost btn--sm" data-se-close aria-label="Закрыть">Закрыть</button>' +
                "</header>" +
                '<p class="sb-modal__note">Займёт время в календаре — клиенты не смогут записаться на этот интервал.</p>' +
                '<div class="sb-modal__body" id="se-body"></div>' +
                '<div class="sb-modal__status" id="se-status" role="status" hidden></div>' +
                '<footer class="sb-modal__foot">' +
                '<button type="button" class="btn btn--ghost" data-se-close>Отмена</button>' +
                '<button type="button" class="btn btn--primary" data-se-submit>Создать</button>' +
                "</footer>" +
                "</div></div>"
        );
        document.body.appendChild(modal);

        var state = {
            calendars: [],
            calendar_id: null,
            title: "",
            block_date: "",
            start_time: "",
            end_time: "",
            notes: "",
        };

        function setStatus(msg, isError) {
            var box = modal.querySelector("#se-status");
            if (!msg) {
                box.hidden = true;
                box.textContent = "";
                return;
            }
            box.hidden = false;
            box.textContent = msg;
            box.className = "sb-modal__status" + (isError ? " is-error" : "");
        }

        function render() {
            var body = modal.querySelector("#se-body");
            var calOpts = state.calendars
                .map(function (c) {
                    var sel = String(c.id) === String(state.calendar_id) ? " selected" : "";
                    return '<option value="' + c.id + '"' + sel + ">" + esc(c.name) + "</option>";
                })
                .join("");
            body.innerHTML =
                '<div class="form-field">' +
                '<label class="form-field__label" for="se-calendar">Календарь</label>' +
                '<select class="input" id="se-calendar"><option value="">Выберите…</option>' +
                calOpts +
                "</select></div>" +
                '<div class="form-field">' +
                '<label class="form-field__label" for="se-title-input">Название</label>' +
                '<input class="input" id="se-title-input" type="text" maxlength="255" placeholder="Например: супервизия" value="' +
                esc(state.title) +
                '"></div>' +
                '<div class="form-field">' +
                '<label class="form-field__label" for="se-date">Дата</label>' +
                '<input class="input" id="se-date" type="date" value="' +
                esc(state.block_date) +
                '"></div>' +
                '<div class="form-field form-field--row">' +
                '<div><label class="form-field__label" for="se-start">Начало</label>' +
                '<input class="input" id="se-start" type="time" step="900" value="' +
                esc(state.start_time) +
                '"></div>' +
                '<div><label class="form-field__label" for="se-end">Конец</label>' +
                '<input class="input" id="se-end" type="time" step="900" value="' +
                esc(state.end_time) +
                '"></div></div>' +
                '<div class="form-field">' +
                '<label class="form-field__label" for="se-notes">Заметки (необязательно)</label>' +
                '<textarea class="input" id="se-notes" rows="3" maxlength="1000">' +
                esc(state.notes) +
                "</textarea></div>";
        }

        function readFields() {
            var cal = modal.querySelector("#se-calendar");
            var title = modal.querySelector("#se-title-input");
            var date = modal.querySelector("#se-date");
            var start = modal.querySelector("#se-start");
            var end = modal.querySelector("#se-end");
            var notes = modal.querySelector("#se-notes");
            state.calendar_id = cal && cal.value ? parseInt(cal.value, 10) : null;
            state.title = title ? title.value.trim() : "";
            state.block_date = date ? date.value : "";
            state.start_time = start ? start.value : "";
            state.end_time = end ? end.value : "";
            state.notes = notes ? notes.value.trim() : "";
        }

        function close() {
            modal.remove();
        }

        modal.addEventListener("click", function (e) {
            if (e.target.closest("[data-se-close]")) close();
        });

        modal.querySelector("[data-se-submit]").addEventListener("click", function () {
            readFields();
            setStatus("", false);
            if (!state.calendar_id) {
                setStatus("Выберите календарь", true);
                return;
            }
            if (!state.title) {
                setStatus("Укажите название", true);
                return;
            }
            if (!state.block_date || !state.start_time || !state.end_time) {
                setStatus("Укажите дату и время", true);
                return;
            }
            var btn = modal.querySelector("[data-se-submit]");
            btn.disabled = true;
            fetch("/api/specialist/events/", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRF-Token": csrfToken(),
                },
                credentials: "same-origin",
                body: JSON.stringify({
                    csrf_token: csrfToken(),
                    calendar_id: state.calendar_id,
                    title: state.title,
                    block_date: state.block_date,
                    start_time: state.start_time.slice(0, 5),
                    end_time: state.end_time.slice(0, 5),
                    notes: state.notes,
                }),
            })
                .then(function (r) {
                    return r.json().then(function (data) {
                        return { ok: r.ok, data: data };
                    });
                })
                .then(function (res) {
                    btn.disabled = false;
                    if (!res.ok) {
                        setStatus((res.data && res.data.error) || "Не удалось создать", true);
                        return;
                    }
                    close();
                    if (window.showToast) {
                        window.showToast("Мероприятие создано", "success");
                    }
                    window.location.reload();
                })
                .catch(function () {
                    btn.disabled = false;
                    setStatus("Ошибка сети", true);
                });
        });

        fetch("/api/specialist/calendars/", { credentials: "same-origin" })
            .then(function (r) {
                return r.json();
            })
            .then(function (data) {
                state.calendars = (data && data.calendars) || [];
                var active = state.calendars.filter(function (c) {
                    return c.is_active !== false;
                });
                if (active.length === 1) state.calendar_id = active[0].id;
                else if (state.calendars.length === 1) state.calendar_id = state.calendars[0].id;
                render();
            })
            .catch(function () {
                setStatus("Не удалось загрузить календари", true);
                render();
            });

        render();
    }

    function bind() {
        document.querySelectorAll("[data-specialist-event]").forEach(function (btn) {
            btn.addEventListener("click", function (e) {
                e.preventDefault();
                openModal();
            });
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", bind);
    } else {
        bind();
    }

    window.openSpecialistEventModal = openModal;
})();
