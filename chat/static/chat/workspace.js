(function () {
    const searchInput = document.getElementById('room-search');
    if (!searchInput) return;

    const roomLinks = Array.from(document.querySelectorAll('[data-room-name]'));
    const noResults = document.getElementById('no-results');

    searchInput.addEventListener('input', function () {
        const term = searchInput.value.trim().toLocaleLowerCase('pt-BR');
        let visibleCount = 0;

        roomLinks.forEach(function (roomLink) {
            const matches = roomLink.dataset.roomName.includes(term);
            roomLink.hidden = !matches;
            if (matches) visibleCount += 1;
        });

        if (noResults) noResults.hidden = visibleCount !== 0;
    });
}());
