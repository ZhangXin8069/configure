/**
 * i18n.js — Internationalization module
 * Handles Chinese/English language switching via data-i18n attributes
 */
const I18N = (function() {
  let currentLang = 'zh';
  let translations = {};

  async function init() {
    // Determine initial language
    const saved = localStorage.getItem('lang');
    if (saved === 'zh' || saved === 'en') {
      currentLang = saved;
    } else if (navigator.language.startsWith('zh')) {
      currentLang = 'zh';
    } else {
      currentLang = 'en';
    }

    await loadTranslations();
    applyTranslations();
    updateLangToggle();
    document.documentElement.lang = currentLang;
  }

  async function loadTranslations() {
    try {
      const resp = await fetch('data/translations.json');
      const data = await resp.json();
      translations = data;
    } catch (e) {
      console.error('Failed to load translations:', e);
    }
  }

  function applyTranslations() {
    const langData = translations[currentLang] || {};
    document.querySelectorAll('[data-i18n]').forEach(el => {
      const key = el.getAttribute('data-i18n');
      if (langData[key]) {
        // Check if element should use innerHTML for rich content
        if (el.hasAttribute('data-i18n-html')) {
          el.innerHTML = langData[key];
        } else {
          el.textContent = langData[key];
        }
      }
    });

    // Handle placeholder attributes
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
      const key = el.getAttribute('data-i18n-placeholder');
      if (langData[key]) {
        el.placeholder = langData[key];
      }
    });

    // Handle title attributes
    document.querySelectorAll('[data-i18n-title]').forEach(el => {
      const key = el.getAttribute('data-i18n-title');
      if (langData[key]) {
        el.title = langData[key];
      }
    });
  }

  function t(key) {
    return (translations[currentLang] && translations[currentLang][key]) || key;
  }

  function getLang() {
    return currentLang;
  }

  async function toggle() {
    currentLang = currentLang === 'zh' ? 'en' : 'zh';
    localStorage.setItem('lang', currentLang);
    document.documentElement.lang = currentLang;
    applyTranslations();
    updateLangToggle();

    // Notify other modules of language change
    document.dispatchEvent(new CustomEvent('langChanged', { detail: { lang: currentLang } }));
  }

  function updateLangToggle() {
    const btn = document.getElementById('lang-toggle');
    if (btn) {
      btn.textContent = currentLang === 'zh' ? 'EN' : '中文';
      btn.setAttribute('aria-label', currentLang === 'zh' ? 'Switch to English' : '切换到中文');
    }
  }

  // Initialize on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  return { init, toggle, t, getLang, applyTranslations };
})();
