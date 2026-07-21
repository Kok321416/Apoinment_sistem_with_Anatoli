(function (global) {
    function ensureStack() {
        let stack = document.getElementById('toast-stack');
        if (!stack) {
            stack = document.createElement('div');
            stack.id = 'toast-stack';
            stack.className = 'toast-stack';
            stack.setAttribute('aria-live', 'polite');
            document.body.appendChild(stack);
        }
        return stack;
    }

    function showToast(message, type) {
        const stack = ensureStack();
        const toast = document.createElement('div');
        toast.className = 'toast' + (type === 'error' ? ' toast--error' : ' toast--success');
        toast.textContent = message;
        stack.appendChild(toast);
        window.setTimeout(function () {
            toast.remove();
            if (!stack.children.length) {
                stack.remove();
            }
        }, 3200);
    }

    global.showToast = showToast;
})(window);
