document.addEventListener('DOMContentLoaded', () => {
  const menu = document.querySelector('.mobile-menu');
  menu?.addEventListener('click', () => {
    const open = document.body.classList.toggle('menu-open');
    menu.setAttribute('aria-expanded', String(open));
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      document.body.classList.remove('menu-open');
      menu?.setAttribute('aria-expanded', 'false');
    }
  });
});
