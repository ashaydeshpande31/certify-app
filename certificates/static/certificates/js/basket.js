/* Basket game for file pickers.
   Choose a file as usual, then (optionally) drag its card into the basket. Winning or not changes
   nothing: the file is attached the moment it is chosen. */
(function () {
  'use strict';
  var inputs = document.querySelectorAll('input[type=file]');
  if (!inputs.length) return;
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  var HOOP =
    '<svg class="bk-hoop" viewBox="0 0 120 112" aria-hidden="true">' +
    '<rect class="bk-board" x="28" y="3" width="64" height="46" rx="5"/>' +
    '<rect class="bk-board" x="47" y="24" width="26" height="17" rx="2"/>' +
    '<g class="bk-net"><path d="M33 57 L47 101M45 60 L55 103M60 61 L60 104M75 60 L65 103M87 57 L73 101"/>' +
    '<path d="M37 71 Q60 77 83 71M41 85 Q60 91 79 85M46 97 Q60 102 74 97"/></g>' +
    '<ellipse class="bk-rim" cx="60" cy="56" rx="30" ry="6"/></svg>';
  var DOC =
    '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/></svg>';

  function size(n) {
    return n < 1024 * 1024 ? Math.max(1, Math.round(n / 1024)) + ' KB' : (n / 1048576).toFixed(1) + ' MB';
  }
  function el(tag, cls, html) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html != null) e.innerHTML = html;
    return e;
  }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }

  inputs.forEach(function (input, idx) {
    var panel = el('div', 'bk-panel');
    panel.hidden = true;
    var hoopWrap = el('div', 'bk-hoop-wrap', HOOP);
    var cards = el('div', 'bk-cards');
    var status = el('p', 'bk-status');
    status.setAttribute('role', 'status');
    var remove = el('button', 'bk-remove btn btn-sm btn-ghost', 'Remove');
    remove.type = 'button';
    var foot = el('div', 'bk-foot');
    foot.appendChild(status);
    foot.appendChild(remove);
    panel.appendChild(hoopWrap);
    panel.appendChild(cards);
    panel.appendChild(foot);
    var anchor = input.closest('.file-drop') || input;
    anchor.parentNode.insertBefore(panel, anchor.nextSibling);

    var hoop = hoopWrap.querySelector('.bk-rim');
    var net = hoopWrap.querySelector('.bk-net');
    var scored = 0, total = 0;

    function say() {
      if (!total) return;
      var many = total > 1;
      if (scored === total) status.textContent = '🏀 Nice shot! ' + (many ? 'All ' + total + ' files are' : 'Your file is') + ' attached.';
      else status.textContent = '✓ ' + (many ? total + ' files' : 'File') + ' attached. Optional: drag ' + (many ? 'a card' : 'the card') + ' into the basket.';
    }
    function confetti() {
      var r = hoop.getBoundingClientRect(), host = hoopWrap.getBoundingClientRect();
      var colors = ['#C9A227', '#E5484D', '#4A66E8', '#3FB68B'];
      for (var i = 0; i < 9; i++) {
        var d = el('span', 'bk-dot');
        d.style.left = (r.left - host.left + r.width / 2) + 'px';
        d.style.top = (r.top - host.top + r.height / 2) + 'px';
        d.style.background = colors[i % colors.length];
        hoopWrap.appendChild(d);
        var a = (Math.PI * 2 * i) / 9, dist = 34 + Math.random() * 26;
        var anim = d.animate([
          { transform: 'translate(0,0) scale(1)', opacity: 1 },
          { transform: 'translate(' + Math.cos(a) * dist + 'px,' + (Math.sin(a) * dist - 18) + 'px) scale(.4)', opacity: 0 }
        ], { duration: 650, easing: 'ease-out' });
        anim.onfinish = (function (n) { return function () { n.remove(); }; })(d);
      }
    }
    function score(card) {
      if (card.dataset.done) return;
      card.dataset.done = '1';
      var finish = function () {
        card.classList.remove('dragging');
        card.classList.add('in-basket');
        card.style.transform = '';
        card.style.opacity = '';
        card.setAttribute('aria-label', card.dataset.name + ' is in the basket');
        card.removeAttribute('tabindex');
        card.querySelector('.bk-hint').textContent = 'In the basket ✓';
        scored++; say();
        if (!reduce && net.animate) {
          net.animate([{ transform: 'scaleY(1)' }, { transform: 'scaleY(1.18) skewX(5deg)' }, { transform: 'scaleY(.94) skewX(-4deg)' }, { transform: 'scaleY(1)' }], { duration: 520, easing: 'ease-out' });
          confetti();
        }
      };
      if (reduce || !card.animate) return finish();
      var c = card.getBoundingClientRect(), h = hoop.getBoundingClientRect();
      var base = (card.style.transform.match(/translate\(([-\d.]+)px,\s*([-\d.]+)px\)/) || [0, 0, 0]);
      var tx = (h.left + h.width / 2) - (c.left + c.width / 2) + Number(base[1]);
      var ty = (h.top + h.height / 2) - (c.top + c.height / 2) + Number(base[2]);
      card.style.transition = 'none';
      var a = card.animate([
        { transform: card.style.transform || 'none', opacity: 1 },
        { transform: 'translate(' + tx + 'px,' + ty + 'px) scale(.28) rotate(200deg)', opacity: .25 }
      ], { duration: 420, easing: 'cubic-bezier(.4,0,.8,.6)' });
      a.onfinish = finish;
    }
    function inHoop(x, y) {          // where the finger / cursor is, not where the wide card's middle is
      var h = hoopWrap.getBoundingClientRect(), pad = 26;
      return x > h.left - pad && x < h.right + pad && y > h.top - pad && y < h.bottom + pad;
    }
    function makeCard(file) {
      var card = el('div', 'bk-card');
      card.tabIndex = 0;
      card.setAttribute('role', 'button');
      card.dataset.name = file.name;
      card.setAttribute('aria-label', file.name + '. Press Enter to drop it in the basket, or drag it there.');
      card.innerHTML = '<span class="bk-card-icon">' + DOC + '</span><span class="bk-card-text"><b>' + esc(file.name) + '</b><small>' + size(file.size) + ' · <span class="bk-hint">Drag me into the basket</span></small></span>';
      var sx = 0, sy = 0, px = 0, py = 0, active = false;
      card.addEventListener('pointerdown', function (e) {
        if (card.dataset.done || (e.button && e.button !== 0)) return;
        active = true; sx = e.clientX; sy = e.clientY;
        card.setPointerCapture(e.pointerId);
        card.style.transition = 'none';
        card.classList.add('dragging');
        e.preventDefault();
      });
      card.addEventListener('pointermove', function (e) {
        if (!active) return;
        var dx = e.clientX - sx, dy = e.clientY - sy;
        card.style.transform = 'translate(' + dx + 'px,' + dy + 'px) rotate(' + Math.max(-14, Math.min(14, dx * 0.06)) + 'deg)';
        px = e.clientX; py = e.clientY;
        hoopWrap.classList.toggle('hot', inHoop(px, py));
      });
      function release() {
        if (!active) return;
        active = false;
        hoopWrap.classList.remove('hot');
        if (inHoop(px, py)) { score(card); return; }
        card.classList.remove('dragging');
        card.style.transition = reduce ? 'none' : 'transform .38s cubic-bezier(.3,1.5,.5,1)';
        card.style.transform = '';
      }
      card.addEventListener('pointerup', release);
      card.addEventListener('pointercancel', release);
      card.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); score(card); }
      });
      return card;
    }
    function rebuild() {
      cards.textContent = '';
      scored = 0;
      total = input.files ? input.files.length : 0;
      if (!total) { panel.hidden = true; return; }
      Array.prototype.forEach.call(input.files, function (f) { cards.appendChild(makeCard(f)); });
      panel.hidden = false;
      say();
    }
    input.addEventListener('change', rebuild);
    remove.addEventListener('click', function () {
      input.value = '';
      input.dispatchEvent(new Event('change', { bubbles: true }));
      input.focus();
    });
  });
})();
