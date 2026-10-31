// Reading progress bar and back-to-top button on article pages.
(function () {
  'use strict';

  // One viewport height of scrolling before the back-to-top button appears,
  // so it doesn't pop in on a short scroll.
  var BACK_TO_TOP_THRESHOLD_RATIO = 1;

  // Scoped to the article body itself, not the whole page, which would also
  // count the header and related articles toward "reading progress".
  var content = document.querySelector('.blog-post-container');
  var bar = document.querySelector('.reading-progress-bar');
  var button = document.querySelector('.back-to-top');
  if (!content || !bar || !button) return;

  var ticking = false;

  // Measured every frame rather than cached once, so it stays correct as
  // images load and MathJax typesets, both of which change the height.
  function update() {
    ticking = false;

    var rect = content.getBoundingClientRect();
    var contentTop = rect.top + window.scrollY;
    var progress =
      rect.height > 0
        ? Math.min(1, Math.max(0, (window.scrollY - contentTop) / rect.height))
        : 0;
    bar.style.setProperty('--reading-progress', String(progress));

    var pastThreshold = window.scrollY > window.innerHeight * BACK_TO_TOP_THRESHOLD_RATIO;
    button.classList.toggle('is-visible', pastThreshold);
  }

  function onScrollOrResize() {
    if (!ticking) {
      ticking = true;
      requestAnimationFrame(update);
    }
  }

  button.addEventListener('click', function () {
    var reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
    // 'auto' would defer to the page's smooth scroll-behavior and still
    // animate; 'instant' is the only value that forces an immediate jump.
    window.scrollTo({ top: 0, behavior: reduceMotion ? 'instant' : 'smooth' });
  });

  update();
  window.addEventListener('scroll', onScrollOrResize, { passive: true });
  window.addEventListener('resize', onScrollOrResize);
})();
