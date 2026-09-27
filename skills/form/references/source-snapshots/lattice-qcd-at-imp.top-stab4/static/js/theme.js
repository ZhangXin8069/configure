/**
 * theme.js — Dark/Light mode toggle module
 * Uses CSS custom properties via [data-theme] attribute on <html>
 */
const Theme = (function() {
  let currentTheme = 'light';
  let isExplicit = false;

  function init() {
    // Check localStorage first
    const saved = localStorage.getItem('theme');
    const explicit = localStorage.getItem('theme-explicit') === 'true';

    if (saved && (saved === 'dark' || saved === 'light')) {
      currentTheme = saved;
      isExplicit = explicit;
    } else {
      // Use system preference
      currentTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }

    applyTheme();
    updateToggle();

    // Listen for system theme changes
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
      if (!isExplicit) {
        currentTheme = e.matches ? 'dark' : 'light';
        applyTheme();
        updateToggle();
      }
    });
  }

  function applyTheme() {
    document.documentElement.setAttribute('data-theme', currentTheme);

    // Update Bulma-specific elements
    if (currentTheme === 'dark') {
      document.querySelectorAll('.hero.is-light').forEach(el => {
        el.classList.add('hero-dark-override');
      });
    } else {
      document.querySelectorAll('.hero.is-light').forEach(el => {
        el.classList.remove('hero-dark-override');
      });
    }
  }

  function toggle() {
    currentTheme = currentTheme === 'dark' ? 'light' : 'dark';
    isExplicit = true;
    localStorage.setItem('theme', currentTheme);
    localStorage.setItem('theme-explicit', 'true');
    applyTheme();
    updateToggle();
  }

  function updateToggle() {
    const btn = document.getElementById('theme-toggle');
    if (!btn) return;

    const icon = btn.querySelector('svg, i');
    if (icon) {
      if (currentTheme === 'dark') {
        icon.setAttribute('class', 'fas fa-sun');
        btn.setAttribute('aria-label', 'Switch to light mode');
        btn.setAttribute('title', I18N ? I18N.t('theme.light') : 'Light Mode');
      } else {
        icon.setAttribute('class', 'fas fa-moon');
        btn.setAttribute('aria-label', 'Switch to dark mode');
        btn.setAttribute('title', I18N ? I18N.t('theme.dark') : 'Dark Mode');
      }
    }
  }

  function getTheme() {
    return currentTheme;
  }

  // Initialize on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Update toggle when language changes
  document.addEventListener('langChanged', updateToggle);

  return { init, toggle, getTheme, applyTheme };
})();
