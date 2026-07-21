(function (global) {
    class ServicesApi {
        constructor(csrfToken) {
            this.csrfToken = csrfToken;
        }

        headers() {
            return {
                'Content-Type': 'application/json',
                'X-CSRF-Token': this.csrfToken,
            };
        }

        async request(url, options) {
            const response = await fetch(url, options);
            let data = null;
            try {
                data = await response.json();
            } catch (e) {
                data = null;
            }
            if (!response.ok) {
                let detail = data && (data.detail || data.error || data.message);
                if (Array.isArray(detail)) {
                    detail = detail.join(', ');
                }
                throw new Error(detail || 'Ошибка запроса');
            }
            return data;
        }

        getCatalog() {
            return this.request('/services/catalog');
        }

        getService(id) {
            return this.request('/services/' + id);
        }

        createService(payload) {
            return this.request('/services/new', {
                method: 'POST',
                headers: this.headers(),
                body: JSON.stringify(Object.assign({ csrf_token: this.csrfToken }, payload)),
            });
        }

        updateService(id, payload) {
            return this.request('/services/' + id, {
                method: 'PUT',
                headers: this.headers(),
                body: JSON.stringify(Object.assign({ csrf_token: this.csrfToken }, payload)),
            });
        }

        deleteService(id) {
            return this.request('/services/' + id, {
                method: 'DELETE',
                headers: this.headers(),
            });
        }

        duplicateService(id) {
            return this.request('/services/' + id + '/duplicate', {
                method: 'POST',
                headers: this.headers(),
            });
        }

        getStatistics(id) {
            return this.request('/services/' + id + '/statistics');
        }

        bulkAction(payload) {
            return this.request('/services/bulk', {
                method: 'POST',
                headers: this.headers(),
                body: JSON.stringify(Object.assign({ csrf_token: this.csrfToken }, payload)),
            });
        }

        reorder(order) {
            return this.request('/services/reorder', {
                method: 'PUT',
                headers: this.headers(),
                body: JSON.stringify({ order: order, csrf_token: this.csrfToken }),
            });
        }
    }

    global.ServicesApi = ServicesApi;
})(window);
