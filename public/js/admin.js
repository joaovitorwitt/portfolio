// The article form: fills the fields in from the chosen artigo.md's front matter,
// says which of its images are chosen, and counts the description's characters.
// Only a convenience: the server reads the same front matter when a field is empty.
(function () {
  'use strict';

  var form = document.getElementById('article-form');
  if (!form) return;

  var field = function (id) { return document.getElementById(id); };
  var markdown = field('markdown');
  var images = field('images');
  var imageStatus = field('image-status');
  var title = field('title');
  var slug = field('slug');
  var description = field('description');
  var count = field('description-count');

  var referenced = [];

  function unquote(value) {
    value = value.trim();
    var first = value.charAt(0);
    if (value.length >= 2 && (first === '"' || first === "'") && value.charAt(value.length - 1) === first) {
      return value.slice(1, -1);
    }
    return value;
  }

  function frontMatter(text) {
    var match = /^---[ \t]*\r?\n([\s\S]*?)\r?\n---[ \t]*(\r?\n|$)/.exec(text);
    var fields = {};
    if (!match) return fields;
    match[1].split(/\r?\n/).forEach(function (line) {
      var pair = /^([A-Za-z_]\w*)\s*:\s*(.*)$/.exec(line);
      if (pair) fields[pair[1]] = pair[2].trim();
    });
    return fields;
  }

  function tagsOf(value) {
    value = value.trim().replace(/^\[/, '').replace(/\]$/, '');
    var seen = [];
    value.split(',').forEach(function (part) {
      var tag = unquote(part).replace(/\s+/g, ' ').trim().toLowerCase();
      if (tag && seen.indexOf(tag) === -1) seen.push(tag);
    });
    return seen.join(', ');
  }

  function slugify(text) {
    return text.normalize('NFKD').replace(/[̀-ͯ]/g, '')
      .toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
  }

  // Must match publish.image_key(): the name without folders, its stem
  // slugified and its extension lowercased.
  function imageKey(path) {
    var name = decodeURIComponent(path.split('/').pop());
    var dot = name.lastIndexOf('.');
    var stem = dot === -1 ? '' : name.slice(0, dot);
    var ext = dot === -1 ? name : name.slice(dot + 1);
    return (slugify(stem) || 'image') + '.' + ext.toLowerCase();
  }

  function referencedImages(text) {
    var found = [];
    // Same as publish.IMAGE_REF: a path with spaces is written as <path>.
    var pattern = /!\[[^\]]*\]\(\s*(?:<([^>\n]+)>|([^)\s]+))/g;
    var match;
    while ((match = pattern.exec(text))) {
      var path = match[1] || match[2];
      if (!/^[a-z][a-z0-9+.-]*:/i.test(path) && path.charAt(0) !== '/' && found.indexOf(path) === -1) {
        found.push(path);
      }
    }
    return found;
  }

  function set(input, value) {
    if (value) input.value = value;
  }

  function showImageStatus() {
    if (!referenced.length) return;
    var chosen = Array.prototype.map.call(images.files, function (file) { return imageKey(file.name); });
    var missing = referenced.filter(function (path) { return chosen.indexOf(imageKey(path)) === -1; });
    imageStatus.textContent = missing.length
      ? 'The text uses ' + referenced.length + ' image(s). Not chosen yet: ' + missing.join(', ')
      : 'All ' + referenced.length + ' image(s) the text uses are chosen.';
  }

  function updateCount() {
    var limit = Number(description.dataset.limit);
    var length = description.value.length;
    count.textContent = '(' + length + ' / ' + limit + ')';
    count.classList.toggle('over-limit', length > limit);
  }

  markdown.addEventListener('change', function () {
    var file = markdown.files[0];
    if (!file) return;
    file.text().then(function (text) {
      var fields = frontMatter(text);
      set(title, unquote(fields.titulo || ''));
      set(description, unquote(fields.descricao || ''));
      set(field('tags'), tagsOf(fields.tags || ''));
      if (/^\d{4}-\d{2}-\d{2}$/.test(unquote(fields.data || ''))) {
        field('date').value = unquote(fields.data);
      }
      if (!slug.value && title.value) slug.value = slugify(title.value);
      referenced = referencedImages(text);
      if (!referenced.length) imageStatus.textContent = 'The text uses no local images.';
      showImageStatus();
      updateCount();
    });
  });

  title.addEventListener('change', function () {
    if (!slug.value) slug.value = slugify(title.value);
  });

  images.addEventListener('change', showImageStatus);
  description.addEventListener('input', updateCount);
  updateCount();
})();
