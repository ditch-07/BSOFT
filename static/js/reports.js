document.addEventListener('DOMContentLoaded', () => {
  const dateForm = document.querySelector('.rp form');
  if (dateForm) {
    dateForm.addEventListener('submit', event => {
      const from = dateForm.querySelector('[name="date_from"]');
      const to = dateForm.querySelector('[name="date_to"]');
      if (from && to && Boolean(from.value) !== Boolean(to.value)) {
        event.preventDefault();
        (from.value ? to : from).focus();
        (from.value ? to : from).setCustomValidity('Choose both dates to apply a range.');
        (from.value ? to : from).reportValidity();
      }
    });
    dateForm.querySelectorAll('[name="date_from"],[name="date_to"]').forEach(input => {
      input.addEventListener('input', () => input.setCustomValidity(''));
    });
  }
  const search = document.getElementById('student-search');
  if (!search) return;
  const hidden = search.parentElement.querySelector('[name="student"]');
  const results = document.createElement('ul');
  results.className = 'rp-search-results';
  results.setAttribute('role', 'listbox');
  search.parentElement.append(results);
  let timer;
  search.addEventListener('input', () => {
    clearTimeout(timer);
    hidden.value = '';
    if (search.value.trim().length < 2) { results.replaceChildren(); return; }
    timer = setTimeout(async () => {
      try {
        const endpoint = document.querySelector('.nav-search')?.dataset.searchUrl;
        if (!endpoint) return;
        const response = await fetch(`${endpoint}?q=${encodeURIComponent(search.value.trim())}`, {headers: {'X-Requested-With':'XMLHttpRequest'}});
        if (!response.ok) return;
        const data = await response.json();
        results.replaceChildren(...data.students.map(student => {
          const item = document.createElement('li');
          item.setAttribute('role','option');
          const button = document.createElement('button');
          button.type='button'; button.textContent=`${student.name} · ${student.student_number}`;
          button.addEventListener('click', () => { search.value=student.name; hidden.value=student.id; results.replaceChildren(); });
          item.append(button); return item;
        }));
      } catch (_) { results.replaceChildren(); }
    }, 180);
  });
});
