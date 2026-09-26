(function () {
    const searchInput = document.getElementById('user-search');
    const userItems = Array.from(document.querySelectorAll('.user-item'));
    const checkboxes = Array.from(document.querySelectorAll('.user-checkbox'));
    const selectedCount = document.getElementById('selected-count');
    const noUsers = document.getElementById('no-users');
    const form = document.getElementById('create-room-form');
    const submitButton = document.getElementById('create-submit');

    function updateSelectedCount() {
        if (!selectedCount) return;
        const count = checkboxes.filter(function (checkbox) { return checkbox.checked; }).length;
        selectedCount.textContent = count + (count === 1 ? ' selecionado' : ' selecionados');
    }

    checkboxes.forEach(function (checkbox) { checkbox.addEventListener('change', updateSelectedCount); });

    if (searchInput) {
        searchInput.addEventListener('input', function () {
            const term = searchInput.value.trim().toLocaleLowerCase('pt-BR');
            let visibleCount = 0;
            userItems.forEach(function (item) {
                const matches = item.dataset.userSearch.includes(term);
                item.hidden = !matches;
                if (matches) visibleCount += 1;
            });
            if (noUsers) noUsers.hidden = visibleCount !== 0;
        });
    }

    if (form && submitButton) {
        form.addEventListener('submit', function () {
            submitButton.disabled = true;
            submitButton.textContent = 'Criando...';
        });
    }

    updateSelectedCount();
}());
