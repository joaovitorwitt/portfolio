// Live search on /articles. The form works on its own as a plain GET form;
// this only fetches the results while typing, swaps them in and keeps the URL
// in step so it can still be shared or bookmarked.
(function () {
  'use strict';

  var form = document.querySelector('[data-search-form]');
  var results = document.getElementById('search-results');
  if (!form || !results || !window.fetch || !window.URLSearchParams) return;

  var input = form.querySelector('input[name="q"]');
  var DELAY = 250;
  var timer = null;
  var controller = null;
  var current = normalise(input.value);

  function normalise(value) {
    return value.trim().replace(/\s+/g, ' ');
  }

  function urlFor(query, partial) {
    var params = new URLSearchParams();
    var tag = form.querySelector('input[name="tag"]');
    if (query) params.set('q', query);
    if (tag && tag.value) params.set('tag', tag.value);
    if (partial) params.set('partial', '1');

    var search = params.toString();
    return form.getAttribute('action') + (search ? '?' + search : '');
  }

  function update(force) {
    var query = normalise(input.value);
    if (query === current && !force) return;
    current = query;

    if (controller) controller.abort();
    controller = window.AbortController ? new AbortController() : null;

    fetch(urlFor(query, true), { signal: controller && controller.signal })
      .then(function (response) {
        if (!response.ok) throw new Error('search failed: ' + response.status);
        return response.text();
      })
      .then(function (html) {
        results.innerHTML = html;
        history.replaceState(history.state, '', urlFor(query, false));
      })
      .catch(function (error) {
        // A newer keystroke cancelled this request; that one will answer.
        if (error.name === 'AbortError') return;
        // Anything else: let the browser load the page the normal way.
        window.location.href = urlFor(query, false);
      });
  }

  input.addEventListener('input', function () {
    clearTimeout(timer);
    timer = setTimeout(update, DELAY);
  });

  form.addEventListener('submit', function (event) {
    event.preventDefault();
    clearTimeout(timer);
    update(true);
  });

  input.addEventListener('keydown', function (event) {
    if (event.key !== 'Escape' || !input.value) return;
    event.preventDefault();
    input.value = '';
    clearTimeout(timer);
    update();
  });

  // "/" jumps to the search box, unless the visitor is already typing.
  document.addEventListener('keydown', function (event) {
    if (event.key !== '/' || event.ctrlKey || event.metaKey || event.altKey) return;
    var target = event.target;
    var typing =
      target.isContentEditable ||
      /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName);
    if (typing) return;

    event.preventDefault();
    input.focus();
    input.select();
  });
})();
