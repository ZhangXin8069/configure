/**
 * music.js — Background music player module
 * Controls playback of MP3 tracks with a floating button UI
 */
const MusicPlayer = (function() {
  let audio = null;
  let currentTrack = 0;
  let isPlaying = false;
  let hasInteracted = false;

  const tracks = [
    { file: 'custom/菊次郎的夏天(轻灵版).mp3', name_zh: '菊次郎的夏天 (轻灵版)', name_en: 'Summer (Light)' },
    { file: 'custom/菊次郎的夏天(经典版).mp3', name_zh: '菊次郎的夏天 (经典版)', name_en: 'Summer (Classic)' },
    { file: 'custom/菊次郎的夏天(治愈版).mp3', name_zh: '菊次郎的夏天 (治愈版)', name_en: 'Summer (Healing)' }
  ];

  function init() {
    audio = new Audio();
    audio.volume = 0.3;
    audio.preload = 'none';

    // Random initial track
    currentTrack = Math.floor(Math.random() * tracks.length);

    audio.addEventListener('ended', () => {
      nextTrack();
    });

    audio.addEventListener('error', () => {
      console.warn('Audio playback error, skipping track');
      nextTrack();
    });

    renderPlayer();
    setupListeners();

    // Attempt auto-play on load
    const tryAutoPlay = () => {
      audio.src = tracks[currentTrack].file;
      audio.load();
      audio.play().then(() => {
        isPlaying = true;
        hasInteracted = true;
        updateUI();
      }).catch(() => {
        // Browser blocked auto-play, will wait for user interaction
        isPlaying = false;
        updateUI();
      });
    };

    // Try after a short delay (some browsers allow muted auto-play)
    setTimeout(() => {
      tryAutoPlay();
    }, 500);

    // Listen for first user interaction to retry if auto-play was blocked
    const enableAudio = () => {
      if (!isPlaying) {
        tryAutoPlay();
      }
      document.removeEventListener('click', enableAudio);
      document.removeEventListener('keydown', enableAudio);
      document.removeEventListener('touchstart', enableAudio);
    };
    document.addEventListener('click', enableAudio);
    document.addEventListener('keydown', enableAudio);
    document.addEventListener('touchstart', enableAudio);
  }

  function renderPlayer() {
    const container = document.getElementById('music-player-container');
    if (!container) return;

    container.innerHTML = `
      <div class="music-player" id="music-player">
        <button class="music-btn" id="music-toggle" aria-label="Play music" title="Play background music">
          <i class="fas fa-music"></i>
        </button>
        <div class="music-controls" id="music-controls">
          <button class="music-ctrl-btn" id="music-prev" title="Previous track">
            <i class="fas fa-step-backward"></i>
          </button>
          <button class="music-ctrl-btn" id="music-play" title="Play/Pause">
            <i class="fas fa-play"></i>
          </button>
          <button class="music-ctrl-btn" id="music-next" title="Next track">
            <i class="fas fa-step-forward"></i>
          </button>
          <button class="music-ctrl-btn" id="music-shuffle" title="Shuffle">🔀</button>
          <span class="music-track-name" id="music-track-name"></span>
          <input type="range" class="music-volume" id="music-volume" min="0" max="100" value="30" title="Volume">
        </div>
      </div>
    `;
  }

  function setupListeners() {
    // Use event delegation since elements are dynamically created
    document.addEventListener('click', (e) => {
      const toggle = e.target.closest('#music-toggle');
      const playBtn = e.target.closest('#music-play');
      const prevBtn = e.target.closest('#music-prev');
      const nextBtn = e.target.closest('#music-next');
      const shuffleBtn = e.target.closest('#music-shuffle');

      if (toggle) {
        const controls = document.getElementById('music-controls');
        controls.classList.toggle('visible');
        // Auto-play on first expand
        if (!isPlaying && controls.classList.contains('visible')) {
          play();
        }
      }
      if (playBtn) togglePlay();
      if (prevBtn) prevTrack();
      if (nextBtn) nextTrack();
      if (shuffleBtn) toggleShuffle();
    });

    document.addEventListener('input', (e) => {
      if (e.target.id === 'music-volume') {
        audio.volume = e.target.value / 100;
      }
    });
  }

  function play() {
    if (!audio.src || audio.src === '') {
      audio.src = tracks[currentTrack].file;
      audio.load();
    }
    const promise = audio.play();
    if (promise) {
      promise.then(() => {
        isPlaying = true;
        updateUI();
      }).catch(err => {
        console.warn('Autoplay prevented:', err);
        isPlaying = false;
        updateUI();
      });
    }
  }

  function pause() {
    audio.pause();
    isPlaying = false;
    updateUI();
  }

  function togglePlay() {
    if (isPlaying) {
      pause();
    } else {
      play();
    }
  }

  let trackHistory = [];
  let isShuffle = true;

  function nextTrack() {
    if (isShuffle) {
      // Random shuffle — avoid immediate repeats
      let next;
      if (tracks.length === 1) {
        next = 0;
      } else {
        const available = [];
        for (let i = 0; i < tracks.length; i++) {
          if (i !== currentTrack) available.push(i);
        }
        // Avoid last 2 tracks in history if possible
        const recentSet = new Set(trackHistory.slice(-2));
        const fresh = available.filter(i => !recentSet.has(i));
        const pool = fresh.length > 0 ? fresh : available;
        next = pool[Math.floor(Math.random() * pool.length)];
      }
      trackHistory.push(next);
      if (trackHistory.length > 10) trackHistory.shift();
      currentTrack = next;
    } else {
      currentTrack = (currentTrack + 1) % tracks.length;
    }
    audio.src = tracks[currentTrack].file;
    audio.load();
    if (isPlaying) {
      audio.play().catch(() => {});
    }
    updateUI();
  }

  function prevTrack() {
    // Go back in history if available, otherwise sequential
    if (trackHistory.length > 1) {
      trackHistory.pop(); // remove current
      currentTrack = trackHistory[trackHistory.length - 1];
    } else {
      currentTrack = (currentTrack - 1 + tracks.length) % tracks.length;
    }
    audio.src = tracks[currentTrack].file;
    audio.load();
    if (isPlaying) {
      audio.play().catch(() => {});
    }
    updateUI();
  }

  function toggleShuffle() {
    isShuffle = !isShuffle;
    updateUI();
  }

  function updateUI() {
    const playBtn = document.getElementById('music-play');
    const trackName = document.getElementById('music-track-name');
    const toggleBtn = document.getElementById('music-toggle');
    const shuffleBtn = document.getElementById('music-shuffle');

    if (playBtn) {
      const icon = playBtn.querySelector('svg, i');
      if (icon) {
        icon.setAttribute('class', isPlaying ? 'fas fa-pause' : 'fas fa-play');
      }
    }

    if (shuffleBtn) {
      shuffleBtn.style.opacity = isShuffle ? '1' : '0.4';
      shuffleBtn.title = isShuffle
        ? ((I18N && I18N.getLang ? I18N.getLang() : 'zh') === 'zh' ? '随机播放：开' : 'Shuffle: ON')
        : ((I18N && I18N.getLang ? I18N.getLang() : 'zh') === 'zh' ? '随机播放：关' : 'Shuffle: OFF');
    }

    if (trackName) {
      const lang = I18N && I18N.getLang ? I18N.getLang() : 'zh';
      const track = tracks[currentTrack];
      trackName.textContent = isPlaying
        ? (lang === 'zh' ? track.name_zh : track.name_en)
        : (lang === 'zh' ? '未在播放' : 'Not playing');
    }

    if (toggleBtn) {
      if (isPlaying) {
        toggleBtn.classList.add('playing');
      } else {
        toggleBtn.classList.remove('playing');
      }
    }
  }

  // Update track name when language changes
  document.addEventListener('langChanged', updateUI);

  // Initialize on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  return { init, play, pause, togglePlay, nextTrack, prevTrack, toggleShuffle };
})();
