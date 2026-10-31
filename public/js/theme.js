// Theme toggle. The inline script in <head> has already set
// <html data-theme> before paint; this only handles changes after load.
(function () {
  'use strict';

  var root = document.documentElement;
  var STORAGE_KEY = 'theme';
  var systemDark = matchMedia('(prefers-color-scheme: dark)');

  function apply(theme) {
    root.dataset.theme = theme;
    root.style.colorScheme = theme;
  }

  function savedTheme() {
    try {
      var theme = localStorage.getItem(STORAGE_KEY);
      return theme === 'light' || theme === 'dark' ? theme : null;
    } catch (e) {
      return null;
    }
  }

  document.addEventListener('click', function (event) {
    if (!event.target.closest('.theme-toggle-button')) return;

    var next = root.dataset.theme === 'dark' ? 'light' : 'dark';
    apply(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch (e) {}
  });

  // With no saved choice, keep following the OS as it changes.
  systemDark.addEventListener('change', function (event) {
    if (!savedTheme()) apply(event.matches ? 'dark' : 'light');
  });

  // A toggle in another tab applies here too.
  window.addEventListener('storage', function (event) {
    if (event.key !== STORAGE_KEY) return;
    apply(savedTheme() || (systemDark.matches ? 'dark' : 'light'));
  });
})();
