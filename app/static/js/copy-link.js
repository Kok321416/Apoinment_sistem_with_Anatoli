(function () {
    "use strict";

    window.copyBookingLink = function (button) {
        var link = button.getAttribute("data-link");
        if (link && link.startsWith("/")) {
            link = window.location.protocol + "//" + window.location.host + link;
        }
        if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(link).then(function () {
                showCopySuccess(button);
            }).catch(function () {
                fallbackCopy(link, button);
            });
        } else {
            fallbackCopy(link, button);
        }
    };

    function fallbackCopy(link, button) {
        try {
            var textArea = document.createElement("textarea");
            textArea.value = link;
            textArea.style.position = "fixed";
            textArea.style.left = "-999999px";
            document.body.appendChild(textArea);
            textArea.focus();
            textArea.select();
            var ok = document.execCommand("copy");
            document.body.removeChild(textArea);
            if (ok) showCopySuccess(button);
            else showCopyError(link, button);
        } catch (e) {
            showCopyError(link, button);
        }
    }

    function showCopySuccess(button) {
        var original = button.textContent;
        button.textContent = "Скопировано";
        button.classList.add("btn--success");
        setTimeout(function () {
            button.textContent = original;
            button.classList.remove("btn--success");
        }, 2000);
    }

    function showCopyError(link, button) {
        prompt("Скопируйте ссылку вручную:", link);
        showCopySuccess(button);
    }
})();
