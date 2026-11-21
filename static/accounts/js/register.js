(function () {
    var form = document.querySelector("[data-register-form]");
    if (!form) {
        return;
    }

    form.querySelectorAll("[data-password-toggle]").forEach(function (button) {
        button.addEventListener("click", function () {
            var input = document.getElementById(button.getAttribute("aria-controls"));
            if (!input) {
                return;
            }
            var hidden = input.getAttribute("type") === "password";
            input.setAttribute("type", hidden ? "text" : "password");
            button.textContent = hidden ? "Hide" : "Show";
        });
    });

    form.addEventListener("submit", function () {
        var button = form.querySelector("[data-submit-button]");
        if (!button || button.disabled) {
            return;
        }
        button.disabled = true;
        button.textContent = "Creating account...";
    });
})();
