/**
 * animations.js — Dynamic effects module
 * Canvas particles, scroll-triggered animations, counter animations, parallax
 */
const Animations = (function() {

  // ===== Hero Background: Starfield (Dark) + Sakura (Light) =====
  function initHeroBackground() {
    const starfieldCanvas = document.getElementById('starfield-canvas');
    const sakuraCanvas = document.getElementById('sakura-canvas');
    if (!starfieldCanvas && !sakuraCanvas) return;

    const hero = document.getElementById('hero');
    if (!hero) return;

    let starfieldId, sakuraId;

    // ---- Starfield (Dark Mode) ----
    if (starfieldCanvas) {
      const ctx = starfieldCanvas.getContext('2d');
      let stars = [];
      let mouse = { x: -1000, y: -1000 };

      function resizeStarfield() {
        starfieldCanvas.width = window.innerWidth;
        starfieldCanvas.height = window.innerHeight;
      }

      function createStars() {
        const count = Math.min(Math.floor(starfieldCanvas.width * starfieldCanvas.height / 3000), 300);
        stars = [];
        for (let i = 0; i < count; i++) {
          stars.push({
            x: Math.random() * starfieldCanvas.width,
            y: Math.random() * starfieldCanvas.height,
            radius: Math.random() * 2.2 + 0.5,
            baseOpacity: Math.random() * 0.6 + 0.2,
            twinkleSpeed: Math.random() * 0.02 + 0.005,
            twinklePhase: Math.random() * Math.PI * 2,
            driftX: (Math.random() - 0.5) * 0.15,
            driftY: (Math.random() - 0.5) * 0.08,
            hue: Math.random() < 0.1 ? Math.random() * 60 + 30 : Math.random() * 40 + 200
          });
        }
      }

      function drawStarfield(timestamp) {
        if (document.documentElement.getAttribute('data-theme') !== 'dark') {
          starfieldId = null;
          return;
        }

        ctx.clearRect(0, 0, starfieldCanvas.width, starfieldCanvas.height);
        const t = timestamp * 0.001;

        // Draw stars
        for (const s of stars) {
          // Twinkling
          const twinkle = Math.sin(t * s.twinkleSpeed * 60 + s.twinklePhase) * 0.3 + 0.7;
          const opacity = s.baseOpacity * twinkle;

          // Slow drift
          s.x += s.driftX;
          s.y += s.driftY;
          if (s.x < -10) s.x = starfieldCanvas.width + 10;
          if (s.x > starfieldCanvas.width + 10) s.x = -10;
          if (s.y < -10) s.y = starfieldCanvas.height + 10;
          if (s.y > starfieldCanvas.height + 10) s.y = -10;

          // Mouse interaction (gentle attraction)
          const dx = mouse.x - s.x;
          const dy = mouse.y - s.y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 120 && dist > 0) {
            s.x += dx / dist * 0.08;
            s.y += dy / dist * 0.08;
          }

          // Draw star with glow
          ctx.beginPath();
          ctx.arc(s.x, s.y, s.radius, 0, Math.PI * 2);
          const glow = ctx.createRadialGradient(s.x, s.y, 0, s.x, s.y, s.radius * 3);
          glow.addColorStop(0, `rgba(147, 197, 253, ${opacity})`);
          glow.addColorStop(1, 'rgba(147, 197, 253, 0)');
          ctx.fillStyle = glow;
          ctx.fill();
          ctx.fillStyle = `rgba(191, 219, 254, ${Math.min(opacity + 0.2, 1)})`;
          ctx.fill();
        }

        // Draw constellation-like lines between nearest bright stars
        const brightStars = stars.filter(s => s.radius > 1.4);
        ctx.strokeStyle = 'rgba(147, 197, 253, 0.04)';
        ctx.lineWidth = 0.5;
        for (let i = 0; i < brightStars.length; i++) {
          for (let j = i + 1; j < brightStars.length; j++) {
            const dx = brightStars[i].x - brightStars[j].x;
            const dy = brightStars[i].y - brightStars[j].y;
            const dist = Math.sqrt(dx * dx + dy * dy);
            if (dist < 130) {
              ctx.beginPath();
              ctx.moveTo(brightStars[i].x, brightStars[i].y);
              ctx.lineTo(brightStars[j].x, brightStars[j].y);
              ctx.stroke();
            }
          }
        }

        starfieldId = requestAnimationFrame(drawStarfield);
      }

      function handleStarMouse(e) {
        const rect = starfieldCanvas.getBoundingClientRect();
        mouse.x = e.clientX - rect.left;
        mouse.y = e.clientY - rect.top;
      }

      resizeStarfield();
      createStars();
      starfieldCanvas.addEventListener('mousemove', handleStarMouse);
      window.addEventListener('resize', function() { resizeStarfield(); createStars(); });

      // Visibility pause
      const starObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            if (!starfieldId) starfieldId = requestAnimationFrame(drawStarfield);
          } else {
            if (starfieldId) { cancelAnimationFrame(starfieldId); starfieldId = null; }
          }
        });
      }, { threshold: 0.1 });
      starObserver.observe(starfieldCanvas);

      starfieldId = requestAnimationFrame(drawStarfield);
    }

    // ---- Cherry Blossom / Sakura (Light Mode) ----
    if (sakuraCanvas) {
      const ctx = sakuraCanvas.getContext('2d');
      let petals = [];

      function resizeSakura() {
        sakuraCanvas.width = window.innerWidth;
        sakuraCanvas.height = window.innerHeight;
      }

      function createPetals() {
        const count = Math.min(Math.floor(sakuraCanvas.width * sakuraCanvas.height / 6000), 120);
        petals = [];
        for (let i = 0; i < count; i++) {
          petals.push({
            x: Math.random() * sakuraCanvas.width,
            y: Math.random() * sakuraCanvas.height,
            size: Math.random() * 8 + 4,
            fallSpeed: Math.random() * 0.8 + 0.3,
            swaySpeed: Math.random() * 0.02 + 0.008,
            swayAmp: Math.random() * 30 + 10,
            swayPhase: Math.random() * Math.PI * 2,
            opacity: Math.random() * 0.4 + 0.15,
            rotation: Math.random() * Math.PI * 2,
            rotSpeed: (Math.random() - 0.5) * 0.02,
            hue: Math.random() * 30 + 345, // pink hues around 345-15
            saturation: Math.random() * 40 + 30
          });
        }
      }

      function drawPetal(ctx, x, y, size, rotation, color) {
        ctx.save();
        ctx.translate(x, y);
        ctx.rotate(rotation);
        // Draw petal shape (elongated ellipse)
        ctx.beginPath();
        ctx.ellipse(0, 0, size * 0.35, size * 0.7, 0, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
        // Add a subtle line in the middle
        ctx.beginPath();
        ctx.moveTo(0, -size * 0.5);
        ctx.lineTo(0, size * 0.3);
        ctx.strokeStyle = 'rgba(255, 200, 200, 0.3)';
        ctx.lineWidth = 0.5;
        ctx.stroke();
        ctx.restore();
      }

      function drawSakura(timestamp) {
        if (document.documentElement.getAttribute('data-theme') !== 'light') {
          sakuraId = null;
          return;
        }

        ctx.clearRect(0, 0, sakuraCanvas.width, sakuraCanvas.height);
        const t = timestamp * 0.001;

        for (const p of petals) {
          // Diagonal fall (bottom-right direction)
          p.y += p.fallSpeed;
          p.x += p.fallSpeed * 0.55 + Math.sin(t * p.swaySpeed * 60 + p.swayPhase) * 0.2;

          p.rotation += p.rotSpeed;

          // Reset when out of bounds
          if (p.y > sakuraCanvas.height + 20) {
            p.y = -20;
            p.x = Math.random() * sakuraCanvas.width;
          }
          if (p.x > sakuraCanvas.width + 20) p.x = -20;
          if (p.x < -20) p.x = sakuraCanvas.width + 20;

          // Draw petal
          const color = `hsla(${p.hue}, ${p.saturation}%, 80%, ${p.opacity})`;
          drawPetal(ctx, p.x, p.y, p.size, p.rotation, color);
        }

        sakuraId = requestAnimationFrame(drawSakura);
      }

      resizeSakura();
      createPetals();
      window.addEventListener('resize', () => { resizeSakura(); createPetals(); });

      const sakuraObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            if (!sakuraId) sakuraId = requestAnimationFrame(drawSakura);
          } else {
            if (sakuraId) { cancelAnimationFrame(sakuraId); sakuraId = null; }
          }
        });
      }, { threshold: 0.1 });
      sakuraObserver.observe(sakuraCanvas);

      sakuraId = requestAnimationFrame(drawSakura);
    }

    // Theme change: restart the correct animation loop when switching themes
    new MutationObserver(() => {
      const theme = document.documentElement.getAttribute('data-theme');
      if (starfieldCanvas) {
        if (theme === 'dark' && !starfieldId) starfieldId = requestAnimationFrame(drawStarfield);
      }
      if (sakuraCanvas) {
        if (theme === 'light' && !sakuraId) sakuraId = requestAnimationFrame(drawSakura);
      }
    }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  }

  // ===== Scroll-Triggered Reveal Animations =====
  function initScrollReveal() {
    const revealElements = document.querySelectorAll('.reveal, .reveal-left, .reveal-right, .reveal-up');

    if (revealElements.length === 0) return;

    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('revealed');

          // Stagger children
          const children = entry.target.querySelectorAll('.reveal-child');
          children.forEach((child, index) => {
            child.style.transitionDelay = `${index * 0.1}s`;
            child.classList.add('revealed');
          });

          observer.unobserve(entry.target);
        }
      });
    }, {
      threshold: 0.15,
      rootMargin: '0px 0px -50px 0px'
    });

    revealElements.forEach(el => observer.observe(el));
  }

  // ===== Counter Animations =====
  function initCounters() {
    const counters = document.querySelectorAll('.stat-number[data-target], .counter[data-target]');

    if (counters.length === 0) return;

    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          const counter = entry.target;
          const target = parseInt(counter.getAttribute('data-target'), 10);
          const duration = 2000;
          const start = performance.now();

          function update(now) {
            const elapsed = now - start;
            const progress = Math.min(elapsed / duration, 1);
            // Ease out cubic
            const eased = 1 - Math.pow(1 - progress, 3);
            const current = Math.round(eased * target);
            counter.textContent = current.toLocaleString();

            if (progress < 1) {
              requestAnimationFrame(update);
            }
          }

          requestAnimationFrame(update);
          observer.unobserve(counter);
        }
      });
    }, { threshold: 0.5 });

    counters.forEach(el => observer.observe(el));
  }

  // ===== Parallax Effect =====
  function initParallax() {
    const parallaxElements = document.querySelectorAll('.parallax');

    if (parallaxElements.length === 0) return;

    window.addEventListener('scroll', () => {
      parallaxElements.forEach(el => {
        const speed = parseFloat(el.getAttribute('data-parallax-speed') || '0.3');
        const rect = el.getBoundingClientRect();
        const scrolled = window.pageYOffset;
        const offset = (scrolled - rect.top) * speed;
        el.style.transform = `translateY(${offset}px)`;
      });
    }, { passive: true });
  }

  // ===== Navbar Scroll Effect (glassmorphism) =====
  function initNavbarScroll() {
    const navbar = document.getElementById('main-navbar');
    if (!navbar) return;

    window.addEventListener('scroll', () => {
      if (window.pageYOffset > 50) {
        navbar.classList.add('scrolled');
      } else {
        navbar.classList.remove('scrolled');
      }
    }, { passive: true });
  }

  // ===== Scroll Spy (active nav link) =====
  function initScrollSpy() {
    const sections = document.querySelectorAll('section[id]');
    const navLinks = document.querySelectorAll('.navbar-item[href^="#"]');

    if (sections.length === 0 || navLinks.length === 0) return;

    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          const id = entry.target.getAttribute('id');
          navLinks.forEach(link => {
            link.classList.toggle('is-active', link.getAttribute('href') === `#${id}`);
          });
        }
      });
    }, { threshold: 0.3 });

    sections.forEach(section => observer.observe(section));
  }

  // ===== Smooth Scroll for Nav Links =====
  function initSmoothScroll() {
    document.addEventListener('click', (e) => {
      const link = e.target.closest('a[href^="#"]');
      if (!link) return;

      const targetId = link.getAttribute('href').slice(1);
      if (!targetId) return;

      const target = document.getElementById(targetId);
      if (!target) return;

      e.preventDefault();

      // Close mobile menu if open
      const burger = document.getElementById('navbar-burger');
      const menu = document.getElementById('navbar-menu');
      if (burger && menu && burger.classList.contains('is-active')) {
        burger.classList.remove('is-active');
        menu.classList.remove('is-active');
      }

      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }

  // ===== Tilt Effect for Advisor Cards =====
  function initTiltEffect() {
    const cards = document.querySelectorAll('.tilt-card');

    cards.forEach(card => {
      card.addEventListener('mousemove', (e) => {
        const rect = card.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        const centerX = rect.width / 2;
        const centerY = rect.height / 2;
        const rotateX = ((y - centerY) / centerY) * -5;
        const rotateY = ((x - centerX) / centerX) * 5;

        card.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) scale3d(1.02, 1.02, 1.02)`;
      });

      card.addEventListener('mouseleave', () => {
        card.style.transform = 'perspective(1000px) rotateX(0) rotateY(0) scale3d(1, 1, 1)';
      });
    });
  }

  // ===== Mobile Menu Toggle =====
  function initMobileMenu() {
    const burger = document.getElementById('navbar-burger');
    const menu = document.getElementById('navbar-menu');

    if (!burger || !menu) return;

    burger.addEventListener('click', () => {
      burger.classList.toggle('is-active');
      menu.classList.toggle('is-active');
    });
  }

  // Initialize all
  function init() {
    initHeroBackground();
    initScrollReveal();
    initCounters();
    initParallax();
    initNavbarScroll();
    initScrollSpy();
    initSmoothScroll();
    initTiltEffect();
    initMobileMenu();
  }

  // Initialize on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  return { init };
})();
