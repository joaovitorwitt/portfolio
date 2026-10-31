// Mobile menu: the toggle button opens and closes it, and following any
// .list-link closes it again.
(function () {
  'use strict';

  var button = document.querySelector('.menu-toggle-button');
  var menu = document.querySelector('.menu');
  if (!button || !menu) return;

  function setOpen(open) {
    button.classList.toggle('active', open);
    menu.classList.toggle('active', open);
    button.setAttribute('aria-expanded', String(open));
  }

  button.addEventListener('click', function () {
    setOpen(!menu.classList.contains('active'));
  });

  document.addEventListener('click', function (event) {
    if (event.target.closest('.list-link')) setOpen(false);
  });
})();
