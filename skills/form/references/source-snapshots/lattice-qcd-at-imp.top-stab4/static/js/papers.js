/**
 * papers.js — Publications module
 * Data source: data/papers.json
 */
const Papers = (function() {
  let allPapers = [];
  let students = [];
  let displayCount = 20;

  function t(k) {
    try { return (typeof I18N !== 'undefined' && I18N.t) ? I18N.t(k) : k; }
    catch(e) { return k; }
  }

  function init() { loadPapers(); setupSearch(); }

  function loadPapers() {
    var c = document.getElementById('publications-list');
    if (c) c.innerHTML = '<p style="text-align:center;padding:2rem;"><i class="fas fa-spinner fa-spin"></i> Loading...</p>';
    fetch('data/papers.json')
      .then(function(r) { return r.json(); })
      .then(function(d) {
        allPapers = (d.papers||[]).sort(function(a,b){ return (b.year||0)-(a.year||0); });
        students = d.students||[];
        renderPapers();
        updateStats();
      })
      .catch(function(e) {
        console.error(e);
        if (c) c.innerHTML = '<p style="text-align:center;padding:2rem;">加载失败</p>';
      });
  }

  function updateStats() {
    var cards = document.querySelectorAll('.stat-card');
    if (cards[0]) { var el = cards[0].querySelector('.stat-number'); if (el) el.setAttribute('data-target', allPapers.length); }
    if (cards[1]) {
      var el = cards[1].querySelector('.stat-number');
      var cites = allPapers.reduce(function(s,p){ return s+(p.citation_count||0); }, 0);
      if (el) el.setAttribute('data-target', cites);
    }
  }

  function renderPapers() {
    var c = document.getElementById('publications-list');
    var nr = document.getElementById('pub-no-results');
    if (!c) return;
    if (!allPapers.length) { if (nr) nr.style.display='block'; return; }
    if (nr) nr.style.display='none';

    var shown = allPapers.slice(0, displayCount);
    c.innerHTML = shown.map(function(p, i) {
      var authors = p.authors ? p.authors.split('; ').slice(0,3).join('; ') + (p.authors.split('; ').length>3?' et al.':'') : '';
      var links = [];
      if (p.arxiv_id) links.push('<a href="https://arxiv.org/abs/'+p.arxiv_id+'" target="_blank" class="paper-link"><i class="ai ai-arxiv"></i> arXiv:'+p.arxiv_id+'</a>');
      if (p.doi) links.push('<a href="https://doi.org/'+p.doi+'" target="_blank" class="paper-link"><i class="fas fa-link"></i> DOI</a>');
      if (p.id) links.push('<a href="https://inspirehep.net/literature/'+p.id+'" target="_blank" class="paper-link"><i class="fas fa-external-link-alt"></i> INSPIRE</a>');

      var div = document.createElement('div'); div.textContent = p.title; var title = div.innerHTML;
      div.textContent = authors; var authHtml = div.innerHTML;
      div.textContent = p.journal||''; var jn = div.innerHTML;

      return '<div class="paper-card reveal-child revealed" style="transition-delay:'+i*0.02+'s">'+
        '<div class="paper-year-badge">'+(p.year||'-')+'</div>'+
        '<h4 class="paper-title">'+title+'</h4>'+
        (authors?'<p class="paper-authors">'+authHtml+'</p>':'')+
        (p.journal?'<p class="paper-journal">'+jn+'</p>':'')+
        '<div class="paper-meta"><div class="paper-links">'+links.join(' ')+'</div>'+
        '<div class="paper-citations"><span class="citation-badge">'+(p.citation_count||0)+'</span> '+t('publications.cited')+'</div></div></div>';
    }).join('');

    var btn = document.getElementById('pub-load-more');
    if (btn) { btn.style.display = displayCount < allPapers.length ? 'block' : 'none'; }
  }

  function loadMore() {
    displayCount += 20;
    renderPapers();
  }

  function setupSearch() {
    var input = document.getElementById('pub-search');
    if (!input) return;
    input.addEventListener('input', function(e) {
      var q = e.target.value.toLowerCase();
      if (!q) { displayCount = 20; renderPapers(); return; }
      var filtered = allPapers.filter(function(p) {
        return (p.title&&p.title.toLowerCase().indexOf(q)>-1) || (p.journal&&p.journal.toLowerCase().indexOf(q)>-1);
      });
      var c = document.getElementById('publications-list');
      var nr = document.getElementById('pub-no-results');
      if (!filtered.length) { c.innerHTML=''; if (nr) nr.style.display='block'; return; }
      if (nr) nr.style.display='none';
      c.innerHTML = filtered.map(function(p, i) {
        var authors = p.authors ? p.authors.split('; ').slice(0,3).join('; ') + (p.authors.split('; ').length>3?' et al.':'') : '';
        var links = [];
        if (p.arxiv_id) links.push('<a href="https://arxiv.org/abs/'+p.arxiv_id+'" target="_blank" class="paper-link"><i class="ai ai-arxiv"></i> arXiv:'+p.arxiv_id+'</a>');
        if (p.doi) links.push('<a href="https://doi.org/'+p.doi+'" target="_blank" class="paper-link"><i class="fas fa-link"></i> DOI</a>');
        if (p.id) links.push('<a href="https://inspirehep.net/literature/'+p.id+'" target="_blank" class="paper-link"><i class="fas fa-external-link-alt"></i> INSPIRE</a>');
        var div = document.createElement('div');
        div.textContent = p.title; var title = div.innerHTML;
        div.textContent = authors; var authHtml = div.innerHTML;
        div.textContent = p.journal||''; var jn = div.innerHTML;
        return '<div class="paper-card reveal-child revealed" style="transition-delay:'+i*0.02+'s">'+
          '<div class="paper-year-badge">'+(p.year||'-')+'</div>'+
          '<h4 class="paper-title">'+title+'</h4>'+
          (authors?'<p class="paper-authors">'+authHtml+'</p>':'')+
          (p.journal?'<p class="paper-journal">'+jn+'</p>':'')+
          '<div class="paper-meta"><div class="paper-links">'+links.join(' ')+'</div>'+
          '<div class="paper-citations"><span class="citation-badge">'+(p.citation_count||0)+'</span> '+t('publications.cited')+'</div></div>';
      }).join('');
    });
  }

  document.addEventListener('langChanged', function() { renderPapers(); });
  var btn = document.getElementById('pub-load-more');
  if (btn) btn.addEventListener('click', loadMore);
  init();

  return {
    init: init,
    getStudents: function() { return students; },
    getPaperCount: function() { return allPapers.length; },
    getCitationCount: function() { return allPapers.reduce(function(s,p){ return s+(p.citation_count||0); }, 0); }
  };
})();
