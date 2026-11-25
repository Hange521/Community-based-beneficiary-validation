document.querySelectorAll('[data-async-assignment]').forEach((form) => {
  form.addEventListener('submit', async (event) => {
    event.preventDefault();

    const button = form.querySelector('[type="submit"]');
    const status = form.querySelector('.assignment-save-status');
    button.disabled = true;
    status.textContent = 'Saving assignments...';

    try {
      const response = await fetch(form.action, {
        method: 'POST',
        body: new FormData(form),
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      });
      const result = await response.json();

      if (!response.ok || !result.ok) {
        const errors = Object.values(result.errors || {})
          .flat()
          .map((error) => error.message)
          .join(' ');
        status.textContent = errors || 'Assignments were not saved. Please try again.';
        return;
      }

      status.textContent = result.message;
    } catch {
      status.textContent = 'Could not reach the server. Your assignments were not changed.';
    } finally {
      button.disabled = false;
    }
  });
});