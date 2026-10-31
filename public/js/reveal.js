// Fades .reveal elements in the first time any part of them enters the
// viewport. The hidden state lives in CSS, so pages using this also carry a
// <noscript> override that shows everything when JS is off.
(function () {
  'use strict';

  var elements = document.querySelectorAll('.reveal');
  if (!elements.length) return;

  function show(element) {
    element.classList.add('reveal-visible');
  }

  if (!('IntersectionObserver' in window)) {
    elements.forEach(show);
    return;
  }

  var observer = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        show(entry.target);
        // The animation runs once, so stop watching after the first reveal.
        observer.unobserve(entry.target);
      });
    },
    { threshold: 0 }
  );

  elements.forEach(function (element) {
    observer.observe(element);
  });
})();
