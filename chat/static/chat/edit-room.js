(function () {
    const searchInput = document.getElementById('user-search');
    const userItems = Array.from(document.querySelectorAll('.user-item[data-user-search]'));
    const checkboxes = Array.from(document.querySelectorAll('.user-checkbox'));
    const selectedCount = document.getElementById('selected-count');
    const noUsers = document.getElementById('no-users');
    const form = document.getElementById('edit-room-form');
    const submitButton = document.getElementById('edit-submit');

    function updateSelectedCount() {
        const count = checkboxes.filter(function (checkbox) { return checkbox.checked; }).length + 1;
        if (selectedCount) selectedCount.textContent = count + (count === 1 ? ' participante' : ' participantes');
    }

    checkboxes.forEach(function (checkbox) { checkbox.addEventListener('change', updateSelectedCount); });
    if (searchInput) searchInput.addEventListener('input', function () {
        const term = searchInput.value.trim().toLocaleLowerCase('pt-BR');
        let visible = 0;
        userItems.forEach(function (item) { const match = item.dataset.userSearch.includes(term); item.hidden = !match; if (match) visible += 1; });
        if (noUsers) noUsers.hidden = visible !== 0;
    });
    if (form && submitButton) form.addEventListener('submit', function () { submitButton.disabled = true; submitButton.textContent = 'Salvando...'; });
    updateSelectedCount();
}());
