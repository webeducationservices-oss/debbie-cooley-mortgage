// =============================================
// Debbie Cooley Mortgage — Site Behaviors
// =============================================
(function () {
  'use strict';

  const RECAPTCHA_SITE_KEY = '6Lck8aQsAAAAALMA-T6nwfkSf7bv4K-mOhkszeKh';

  // ---------- Mobile menu ----------
  const menuOpen = document.getElementById('menuOpen');
  const menuClose = document.getElementById('menuClose');
  const mobileNav = document.getElementById('mobileNav');

  function openMenu() { mobileNav && mobileNav.classList.add('open'); document.body.style.overflow = 'hidden'; }
  function closeMenu() { mobileNav && mobileNav.classList.remove('open'); document.body.style.overflow = ''; }

  menuOpen && menuOpen.addEventListener('click', openMenu);
  menuClose && menuClose.addEventListener('click', closeMenu);
  mobileNav && mobileNav.addEventListener('click', (e) => {
    if (e.target === mobileNav) closeMenu();
  });
  document.querySelectorAll('.mobile-nav a:not([href^="#"])').forEach(a => a.addEventListener('click', closeMenu));

  // ---------- Year stamp ----------
  const yr = document.getElementById('year');
  if (yr) yr.textContent = new Date().getFullYear();

  // ---------- Mortgage payment calculator (homepage + pages that use it) ----------
  const fmtUSD = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
  const parseMoney = (val) => Number(String(val).replace(/[^0-9.]/g, '')) || 0;

  function calculatePayment() {
    const price = parseMoney(document.getElementById('calcPrice').value);
    const downPct = Number(document.getElementById('calcDown').value) || 0;
    const rate = Number(document.getElementById('calcRate').value) || 0;
    const years = Number(document.getElementById('calcTerm').value) || 30;
    const loan = Math.max(0, price * (1 - downPct / 100));
    const monthlyRate = rate / 100 / 12;
    const n = years * 12;
    let monthly = monthlyRate === 0 ? loan / n : loan * (monthlyRate * Math.pow(1 + monthlyRate, n)) / (Math.pow(1 + monthlyRate, n) - 1);
    const totalInterest = (monthly * n) - loan;
    document.getElementById('calcAmount').textContent = fmtUSD.format(monthly);
    document.getElementById('calcLoan').textContent = fmtUSD.format(loan);
    document.getElementById('calcInterest').textContent = fmtUSD.format(Math.max(0, totalInterest));
    document.getElementById('calcResult').style.display = 'block';
  }
  const calcBtn = document.getElementById('calcBtn');
  if (calcBtn) {
    calcBtn.addEventListener('click', calculatePayment);
    const priceInput = document.getElementById('calcPrice');
    priceInput && priceInput.addEventListener('blur', () => {
      const num = parseMoney(priceInput.value);
      if (num > 0) priceInput.value = fmtUSD.format(num);
    });
    priceInput && priceInput.addEventListener('focus', () => {
      priceInput.value = String(parseMoney(priceInput.value) || '');
    });
    document.querySelectorAll('#calculator input, #calculator select').forEach(el => {
      el.addEventListener('keydown', (e) => { if (e.key === 'Enter') calculatePayment(); });
    });
  }

  // ---------- Universal AJAX form handler (per FORMS-AND-THANK-YOU.md) ----------
  const FORM_ENDPOINT = 'https://myaieditor.com/api/form-notify';
  const RECAPTCHA_TIMEOUT_MS = 8000;
  const FALLBACK_PHONE = '727-688-2851';
  const FALLBACK_PHONE_HREF = 'tel:7276882851';

  // Resolve a reCAPTCHA v3 token without ever hanging the visitor.
  // If the grecaptcha script is blocked (ad blockers), still loading, or keyed
  // wrong, grecaptcha.execute() can stay pending forever, which leaves the
  // submit button dead and the lead unrecorded. Fall back to an empty token
  // instead: form-notify logs that as missing_recaptcha_token, which stays
  // rescuable from the Spam tab. A hung button is not.
  function getRecaptchaToken() {
    if (typeof grecaptcha === 'undefined' || !grecaptcha || typeof grecaptcha.ready !== 'function') {
      return Promise.resolve('');
    }
    let timer;
    const attempt = new Promise((resolve, reject) => {
      try {
        grecaptcha.ready(() => {
          try {
            Promise.resolve(grecaptcha.execute(RECAPTCHA_SITE_KEY, { action: 'form_submit' })).then(resolve, reject);
          } catch (err) { reject(err); }
        });
      } catch (err) { reject(err); }
    });
    const timeout = new Promise((resolve) => {
      timer = setTimeout(() => resolve(''), RECAPTCHA_TIMEOUT_MS);
    });
    return Promise.race([attempt, timeout])
      .catch((err) => { console.error('reCAPTCHA unavailable:', err); return ''; })
      .then((token) => { clearTimeout(timer); return typeof token === 'string' ? token : ''; });
  }

  // Visible, in-form failure notice. Never use alert(): it can be suppressed by
  // the browser when fired from an async continuation, which would put us right
  // back to losing the lead silently.
  function formErrorBox(form) {
    let box = form.querySelector('.form-error');
    if (box) return box;
    box = document.createElement('div');
    box.className = 'form-error';
    box.setAttribute('role', 'alert');
    box.style.cssText = 'display:none;margin:14px 0 0;padding:12px 14px;border-radius:8px;'
      + 'border-left:3px solid #b3261e;background:#fdeceb;color:#5f1512;'
      + 'font-size:0.9rem;line-height:1.45;text-align:left;';
    const btn = form.querySelector('[type="submit"]');
    if (btn && btn.parentNode) btn.insertAdjacentElement('afterend', box);
    else (form.querySelector('.form-fields') || form).appendChild(box);
    return box;
  }

  function showFormError(form) {
    const box = formErrorBox(form);
    box.innerHTML = 'Sorry, your message did not go through. Please call Debbie at '
      + '<a href="' + FALLBACK_PHONE_HREF + '" style="color:inherit;font-weight:600;text-decoration:underline">'
      + FALLBACK_PHONE + '</a>, or try again in a moment.';
    box.style.display = 'block';
    box.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  function hideFormError(form) {
    const box = form.querySelector('.form-error');
    if (box) box.style.display = 'none';
  }

  document.querySelectorAll('form[data-ajax]').forEach(form => {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();

      // Honeypot: silently bail if filled
      if (form.querySelector('[name="_honey"]')?.value) return;

      const btn = form.querySelector('[type="submit"]');
      const originalHTML = btn ? btn.innerHTML : '';
      if (btn) { btn.disabled = true; btn.textContent = 'Sending…'; }
      hideFormError(form);

      // A submission only counts as delivered when the server both responded OK
      // and did not flag it as rejected. form-notify answers HTTP 200 with
      // { accepted: false, reason } for blocked submissions, so res.ok alone
      // would still show a fake thank-you over a destroyed lead.
      let delivered = false;
      try {
        const token = await getRecaptchaToken();
        const tokenField = form.querySelector('[name="recaptcha_token"]');
        if (tokenField) tokenField.value = token;

        const formData = new FormData(form);
        const data = Object.fromEntries(formData.entries());

        const res = await fetch(FORM_ENDPOINT, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data),
        });
        const j = await res.json().catch(() => ({}));
        delivered = res.ok && j.accepted !== false;
      } catch (err) {
        console.error('Form submit error:', err);
      }

      if (!delivered) {
        if (btn) { btn.disabled = false; btn.innerHTML = originalHTML; }
        showFormError(form);
        return;
      }

      // Show thank-you UI (only on a genuinely accepted lead)
      const fields = form.querySelector('.form-fields');
      const success = form.querySelector('.form-success');
      if (fields) fields.style.display = 'none';
      if (success) {
        success.classList.add('show');
        success.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    });
  });

  // ---------- Smooth scroll offset for sticky header ----------
  document.querySelectorAll('a[href^="#"]').forEach(link => {
    link.addEventListener('click', (e) => {
      const id = link.getAttribute('href');
      if (id === '#' || id.length < 2) return;
      const target = document.querySelector(id);
      if (!target) return;
      e.preventDefault();
      const headerOffset = 96;
      const top = target.getBoundingClientRect().top + window.scrollY - headerOffset;
      window.scrollTo({ top, behavior: 'smooth' });
    });
  });
})();
