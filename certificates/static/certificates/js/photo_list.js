/* Read email addresses out of a photo (JPG/PNG/WebP...) chosen as a participant / recipient list.
   The reading happens in the visitor's own browser (Tesseract.js), so the server stays light.
   input._photo = { state: 'idle' | 'reading' | 'found' | 'none' | 'error', emails: [] } */
(function () {
  'use strict';
  var IMG = /\.(jpe?g|png|webp|bmp|gif)$/i;
  var EMAIL = /[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}/g;
  var workerP = null;

  function isImage(f) { return !!f && (/^image\//.test(f.type || '') || IMG.test(f.name || '')); }

  function loadScript(src) {
    return new Promise(function (res, rej) {
      var s = document.createElement('script');
      s.src = src; s.onload = res; s.onerror = rej;
      document.head.appendChild(s);
    });
  }
  function getWorker() {
    if (!workerP) {
      workerP = loadScript('https://cdn.jsdelivr.net/npm/tesseract.js@5/dist/tesseract.min.js')
        .then(function () { return window.Tesseract.createWorker('eng'); })
        .catch(function (e) { workerP = null; throw e; });
    }
    return workerP;
  }
  // shrink big phone photos first: reading a 1600px picture is much faster than a 4000px one
  function shrink(file) {
    return new Promise(function (res) {
      if (!window.createImageBitmap) return res(file);
      createImageBitmap(file).then(function (bmp) {
        var max = 1600, k = Math.min(1, max / Math.max(bmp.width, bmp.height));
        if (k >= 1) return res(file);
        var c = document.createElement('canvas');
        c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k);
        c.getContext('2d').drawImage(bmp, 0, 0, c.width, c.height);
        c.toBlob(function (b) { res(b || file); }, 'image/png');
      }, function () { res(file); });
    });
  }
  function findEmails(text) {
    var clean = String(text || '').replace(/\s*@\s*/g, '@').replace(/@\s+/g, '@');
    var seen = {}, out = [];
    (clean.match(EMAIL) || []).forEach(function (m) {
      m = m.replace(/[.,;:]+$/, '');
      var k = m.toLowerCase();
      if (!seen[k]) { seen[k] = 1; out.push(m); }
    });
    return out;
  }

  var token = 0;
  function attach(input, hidden, changed) {
    input._photo = { state: 'idle', emails: [] };
    function set(state, emails) {
      input._photo = { state: state, emails: emails || [] };
      if (hidden) hidden.value = (emails || []).join('\n');
      if (changed) changed();
    }
    input.addEventListener('change', function () {
      var f = input.files && input.files[0], mine = ++token;
      if (!isImage(f)) return set('idle');
      set('reading');
      shrink(f).then(function (img) {
        return getWorker().then(function (w) { return w.recognize(img); });
      }).then(function (r) {
        if (mine !== token) return;
        var emails = findEmails(r && r.data && r.data.text);
        set(emails.length ? 'found' : 'none', emails);
      }).catch(function () {
        if (mine === token) set('error');
      });
    });
    // Start fetching the reader only when the person reaches for the file picker (the dialog takes a few
    // seconds anyway), never in the background of every page view: it is a ~6 MB download.
    var warmed = false;
    function warm() { if (warmed) return; warmed = true; getWorker().catch(function () { warmed = false; }); }
    var zone = input.closest('.file-drop') || input;
    ['pointerdown', 'focus', 'keydown'].forEach(function (ev) { zone.addEventListener(ev, warm, { once: true, passive: true }); });
  }

  // one place for the wording shown under the list picker
  function message(f, p, name) {
    if (p.state === 'reading') return { kind: 'info', text: 'Reading the photo for email addresses…' };
    if (p.state === 'found') return { kind: 'ok', text: 'Found ' + p.emails.length + ' email' + (p.emails.length > 1 ? 's' : '') + ' in the photo: ' + p.emails.slice(0, 4).join(', ') + (p.emails.length > 4 ? '…' : '') };
    if (p.state === 'error') return { kind: 'err', text: 'Couldn\'t read "' + name + '" here (the photo reader needs an internet connection). Use an Excel, CSV or PDF list, or type the emails instead.' };
    return { kind: 'err', text: 'No email found in "' + name + '". Choose a clearer photo, or use an Excel, CSV or PDF list.' };
  }
  function paint(box, m) {
    if (!box) return;
    if (!m) { box.style.display = 'none'; box.textContent = ''; return; }
    box.textContent = m.text;
    box.style.display = 'block';
    box.style.color = m.kind === 'ok' ? '#1F9D6B' : m.kind === 'info' ? '#8A94A8' : '';
  }

  window.PhotoList = { attach: attach, isImage: isImage, message: message, paint: paint };
})();
