(function (global) {
    function init(api) {
        var statusEl = document.getElementById('save-status');
        var timer = null;
        var saving = false;

        function setStatus(state, text) {
            if (!statusEl) return;
            statusEl.className = 'profile-save-status' + (state ? ' is-' + state : '');
            statusEl.textContent = text || '';
        }

        function scheduleSave() {
            if (timer) clearTimeout(timer);
            setStatus('saving', 'Сохранение…');
            timer = setTimeout(doSave, 800);
        }

        async function doSave() {
            if (saving) return;
            saving = true;
            try {
                var payload = global.profilePreview.collect();
                var result = await api.saveData(payload);
                setStatus('saved', 'Изменения сохранены');
                if (result.data) {
                    global.profilePage.applyData(result.data);
                }
            } catch (error) {
                setStatus('error', error.message);
                if (global.showToast) global.showToast(error.message, 'error');
            } finally {
                saving = false;
            }
        }

        document.querySelectorAll('.profile-field').forEach(function (el) {
            el.addEventListener('input', scheduleSave);
            el.addEventListener('change', scheduleSave);
        });

        document.addEventListener('profile-photo-cropped', async function (event) {
            var blob = event.detail && event.detail.blob;
            if (!blob) return;
            setStatus('saving', 'Загрузка фото…');
            try {
                var file = new File([blob], 'photo.jpg', { type: 'image/jpeg' });
                var result = await api.uploadAvatar(file);
                setStatus('saved', 'Фото обновлено');
                if (global.showToast) global.showToast('Фото обновлено');
                if (result.data) global.profilePage.applyData(result.data);
            } catch (error) {
                setStatus('error', error.message);
                if (global.showToast) global.showToast(error.message, 'error');
            }
        });

        global.profileAutosave = { saveNow: doSave };
    }

    global.initProfileAutosave = init;
})(window);
