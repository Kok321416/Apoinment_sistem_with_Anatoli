(function (global) {
    class ProfileApi {
        constructor(csrfToken) {
            this.csrfToken = csrfToken;
        }

        headers(json) {
            const h = { 'X-CSRF-Token': this.csrfToken };
            if (json) h['Content-Type'] = 'application/json';
            return h;
        }

        async request(url, options) {
            const response = await fetch(url, options);
            let data = null;
            try { data = await response.json(); } catch (e) { data = null; }
            if (!response.ok) {
                let detail = data && (data.detail || data.message || data.error);
                if (Array.isArray(detail)) detail = detail.join(', ');
                throw new Error(detail || 'Ошибка запроса');
            }
            return data;
        }

        getData() { return this.request('/profile/data'); }

        saveData(payload) {
            return this.request('/profile/data', {
                method: 'PUT',
                headers: this.headers(true),
                body: JSON.stringify(Object.assign({ csrf_token: this.csrfToken }, payload)),
            });
        }

        uploadAvatar(file) {
            const fd = new FormData();
            fd.append('profile_photo', file, 'photo.jpg');
            return this.request('/profile/avatar', {
                method: 'POST',
                headers: this.headers(false),
                body: fd,
            });
        }
    }

    global.ProfileApi = ProfileApi;
})(window);
