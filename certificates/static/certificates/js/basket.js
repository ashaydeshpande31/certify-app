/* Basket game for file pickers.
   Choose a file as usual, then (optionally) drag its card into the basket. Winning or not changes
   nothing: the file is attached the moment it is chosen. */
(function () {
  'use strict';
  var inputs = document.querySelectorAll('input[type=file]');
  if (!inputs.length) return;
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // colours are set on the shapes themselves, so the basket looks right even before the stylesheet loads
  var HOOP =
    '<svg class="bk-hoop" viewBox="0 0 140 130" aria-hidden="true">' +
    '<rect class="bk-board" x="30" y="4" width="80" height="56" rx="6" fill="#ffffff" stroke="#E8672A" stroke-width="3"/>' +
    '<rect class="bk-board" x="55" y="28" width="30" height="20" rx="3" fill="none" stroke="#E8672A" stroke-width="3"/>' +
    '<rect x="64" y="58" width="12" height="7" fill="#E8672A"/>' +
    '<g class="bk-net" fill="none" stroke="#9AA5B8" stroke-width="1.8" stroke-linecap="round" style="transform-origin:50% 0;transform-box:fill-box">' +
    '<path d="M37 69 L54 117M50 72 L62 120M70 73 L70 121M90 72 L78 120M103 69 L86 117"/>' +
    '<path d="M42 84 Q70 91 98 84M47 99 Q70 106 93 99M52 112 Q70 118 88 112"/></g>' +
    '<ellipse class="bk-rim" cx="70" cy="68" rx="35" ry="7" fill="none" stroke="#E8672A" stroke-width="5"/></svg>';
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

  // the dotted path that shows where the file will go while you hold it
  var AIM_DOTS = 10;
  var aim = el('div', 'bk-aim');
  aim.setAttribute('aria-hidden', 'true');
  for (var k = 0; k < AIM_DOTS; k++) aim.appendChild(el('span'));
  document.body.appendChild(aim);
  function showAim(x0, y0, x1, y1, hot) {
    var cx = (x0 + x1) / 2, cy = Math.min(y0, y1) - 70;   // the path bends upwards, like a shot
    aim.classList.toggle('hot', !!hot);
    aim.classList.add('on');
    Array.prototype.forEach.call(aim.children, function (d, i) {
      var t = (i + 1) / (AIM_DOTS + 1), u = 1 - t;
      var x = u * u * x0 + 2 * u * t * cx + t * t * x1, y = u * u * y0 + 2 * u * t * cy + t * t * y1;
      d.style.left = x + 'px'; d.style.top = y + 'px';
      d.style.transform = 'translate(-50%,-50%) scale(' + (1 - t * 0.45) + ')';
    });
  }
  function hideAim() { aim.classList.remove('on'); }

  inputs.forEach(function (input, idx) {
    var panel = el('div', 'bk-panel');
    panel.hidden = true;
    var top = el('div', 'bk-top', '<span class="bk-top-title">Take the shot <small>(optional)</small></span><span class="bk-count" aria-hidden="true">Added <b>0</b></span>');
    var countNum = top.querySelector('b');
    var hoopWrap = el('div', 'bk-hoop-wrap', HOOP);
    var cards = el('div', 'bk-cards');
    var status = el('p', 'bk-status');
    status.setAttribute('role', 'status');
    var remove = el('button', 'bk-remove btn btn-sm btn-ghost', 'Remove');
    remove.type = 'button';
    var foot = el('div', 'bk-foot');
    foot.appendChild(status);
    foot.appendChild(remove);
    panel.appendChild(top);
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
    function plusOne() {
      var t = el('span', 'bk-plus', '+1');
      hoopWrap.appendChild(t);
      if (t.animate) {
        var a = t.animate([{ transform: 'translate(-50%,0)', opacity: 1 }, { transform: 'translate(-50%,-46px)', opacity: 0 }], { duration: 800, easing: 'ease-out' });
        a.onfinish = function () { t.remove(); };
      } else { setTimeout(function () { t.remove(); }, 800); }
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
        scored++; say();
        countNum.textContent = scored;
        var bar = card.querySelector('.bk-bar i'), hint = card.querySelector('.bk-hint');
        card.classList.add('adding');
        hint.textContent = 'Adding…';
        var doneUp = function () { card.classList.remove('adding'); card.classList.add('added'); hint.textContent = 'Added ✓'; };
        if (reduce) { doneUp(); } else {
          setTimeout(function () { bar.style.width = '100%'; }, 30);
          setTimeout(doneUp, 1000);
          plusOne();
          if (top.animate) top.querySelector('.bk-count').animate([{ transform: 'scale(1)' }, { transform: 'scale(1.25)' }, { transform: 'scale(1)' }], { duration: 400, easing: 'ease-out' });
        }
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
      card.innerHTML = '<span class="bk-card-icon">' + DOC + '</span><span class="bk-card-text"><b>' + esc(file.name) + '</b><small>' + size(file.size) + ' · <span class="bk-hint">Hold me and drop me in the basket</span></small></span><span class="bk-state"><span class="bk-bar"><i></i></span><span class="bk-check">✓</span></span>';
      var sx = 0, sy = 0, px = 0, py = 0, active = false;
      card.addEventListener('pointerdown', function (e) {
        if (card.dataset.done || (e.button && e.button !== 0)) return;
        active = true; sx = e.clientX; sy = e.clientY;
        card.setPointerCapture(e.pointerId);
        card.style.transition = 'none';
        card.classList.add('dragging');
        px = e.clientX; py = e.clientY;
        var h0 = hoop.getBoundingClientRect();
        showAim(px, py, h0.left + h0.width / 2, h0.top + h0.height / 2, false);
        e.preventDefault();
      });
      card.addEventListener('pointermove', function (e) {
        if (!active) return;
        var dx = e.clientX - sx, dy = e.clientY - sy;
        card.style.transform = 'translate(' + dx + 'px,' + dy + 'px) rotate(' + Math.max(-14, Math.min(14, dx * 0.06)) + 'deg)';
        px = e.clientX; py = e.clientY;
        var hot = inHoop(px, py);
        hoopWrap.classList.toggle('hot', hot);
        var hr = hoop.getBoundingClientRect();
        showAim(px, py, hr.left + hr.width / 2, hr.top + hr.height / 2, hot);
      });
      function release() {
        if (!active) return;
        active = false;
        hideAim();
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
