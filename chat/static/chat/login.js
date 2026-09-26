(function () {
    const form = document.getElementById('login-form');
    const submit = document.getElementById('login-submit');
    const password = document.getElementById('id_senha');
    const toggle = document.getElementById('toggle-password');

    if (form && submit) {
        form.addEventListener('submit', function () {
            submit.disabled = true;
            submit.textContent = 'Entrando...';
        });
    }

    if (toggle && password) {
        toggle.addEventListener('click', function () {
            const showing = password.type === 'text';
            password.type = showing ? 'password' : 'text';
            toggle.textContent = showing ? '◉' : '◌';
            toggle.setAttribute('aria-label', showing ? 'Mostrar senha' : 'Ocultar senha');
            toggle.title = showing ? 'Mostrar senha' : 'Ocultar senha';
        });
    }
}());
