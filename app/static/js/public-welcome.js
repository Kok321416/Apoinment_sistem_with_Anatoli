(function () {
    "use strict";

    var form = document.getElementById("clientWelcomeForm");
    if (!form) return;

    var emailBlock = document.getElementById("emailBlock");
    var tgBlock = document.getElementById("telegramBlock");
    var phoneInput = document.getElementById("client_phone");

    form.querySelectorAll('input[name="channel"]').forEach(function (radio) {
        radio.addEventListener("change", function () {
            var isEmail = form.channel.value === "email";
            emailBlock.classList.toggle("is-hidden", !isEmail);
            tgBlock.classList.toggle("is-hidden", isEmail);
        });
    });

    if (phoneInput) {
        phoneInput.addEventListener("input", function () {
            var digits = phoneInput.value.replace(/\D/g, "");
            if (phoneInput.value !== digits) {
                phoneInput.value = digits;
            }
        });
        phoneInput.addEventListener("paste", function (event) {
            event.preventDefault();
            var text = (event.clipboardData || window.clipboardData).getData("text") || "";
            phoneInput.value = text.replace(/\D/g, "");
        });
    }

    form.addEventListener("submit", function (event) {
        var phone = phoneInput ? phoneInput.value.trim() : "";
        if (phone && !/^\d{10,15}$/.test(phone)) {
            event.preventDefault();
            window.alert("Телефон должен содержать только цифры (от 10 до 15).");
            if (phoneInput) phoneInput.focus();
        }
    });
})();
