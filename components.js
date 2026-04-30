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
  document.querySelectorAll('form[data-ajax]').forEach(form => {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();

      // Honeypot — silently bail if filled
      if (form.querySelector('[name="_honey"]')?.value) return;

      const btn = form.querySelector('[type="submit"]');
      const originalText = btn ? btn.textContent : '';
      if (btn) { btn.disabled = true; btn.textContent = 'Sending…'; }

      try {
        // Get reCAPTCHA v3 token (invisible)
        if (typeof grecaptcha !== 'undefined') {
          await new Promise((resolve) => grecaptcha.ready(resolve));
          const token = await grecaptcha.execute(RECAPTCHA_SITE_KEY, { action: 'form_submit' });
          const tokenField = form.querySelector('[name="recaptcha_token"]');
          if (tokenField) tokenField.value = token;
        }

        const formData = new FormData(form);
        const data = Object.fromEntries(formData.entries());

        await fetch('https://myaieditor.com/api/form-notify', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data),
        });
      } catch (err) {
        console.error('Form submit error:', err);
      }

      // Show thank-you UI
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
