document.querySelectorAll('.db tr[data-student-url]').forEach((row) => {
    row.addEventListener('click', (event) => {
        if (event.target.closest('a, button, [aria-disabled]') || window.getSelection().toString() || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        window.location.assign(row.dataset.studentUrl);
    });
});
document.querySelectorAll('[data-dismiss-notice]').forEach((button) => {
    button.addEventListener('click', () => button.closest('.db-notice').remove());
});
