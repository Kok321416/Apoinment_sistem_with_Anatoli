(function () {
    function generateTimeOptions(selectElement) {
        for (let hour = 0; hour < 24; hour++) {
            for (let minute = 0; minute < 60; minute += 30) {
                const timeString = String(hour).padStart(2, '0') + ':' + String(minute).padStart(2, '0');
                const option = document.createElement('option');
                option.value = timeString;
                option.textContent = timeString;
                selectElement.appendChild(option);
            }
        }
    }

    function init() {
        for (let i = 0; i < 7; i++) {
            const startSelect = document.getElementById('start_' + i);
            const endSelect = document.getElementById('end_' + i);
            if (startSelect) generateTimeOptions(startSelect);
            if (endSelect) generateTimeOptions(endSelect);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
