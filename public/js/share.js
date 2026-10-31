// Copy-link button in the share bar. The X and LinkedIn links are plain
// anchors and need no script.
(function () {
  'use strict';

  var button = document.querySelector('.share-copy-button');
  var feedback = document.querySelector('.share-buttons-feedback');
  if (!button || !feedback) return;

  var STATES = {
    idle: { label: 'Copy link', message: '' },
    copied: { label: 'Link copied', message: 'Copied!' },
    error: { label: "Couldn't copy link", message: "Couldn't copy — try again" },
  };
  var resetTimer = null;

  // navigator.clipboard.writeText can reject for reasons unrelated to this
  // code (document not focused, no Clipboard API, a denied permission), so
  // the old execCommand technique is the fallback.
  function legacyCopy(text) {
    var textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    var succeeded = false;
    try {
      succeeded = document.execCommand('copy');
    } catch (e) {
      succeeded = false;
    }
    document.body.removeChild(textarea);
    return succeeded;
  }

  function copy(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).then(
        function () {
          return true;
        },
        function () {
          return legacyCopy(text);
        }
      );
    }
    return Promise.resolve(legacyCopy(text));
  }

  // The icon is swapped by CSS keyed off data-status (see site.css).
  function setStatus(status) {
    button.dataset.status = status;
    button.setAttribute('aria-label', STATES[status].label);
    feedback.textContent = STATES[status].message;
  }

  button.addEventListener('click', function () {
    copy(button.dataset.url || location.href).then(function (succeeded) {
      setStatus(succeeded ? 'copied' : 'error');
      clearTimeout(resetTimer);
      resetTimer = setTimeout(function () {
        setStatus('idle');
      }, 2000);
    });
  });
})();
