/* 水浒维基 · 全文搜索（唯一 JS 页面，design.md §5.10） */
let idx = null;
const $q = document.getElementById('q');
const $r = document.getElementById('results');
const $m = document.getElementById('meta');
const esc = s => s.replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function ensure() {
  if (!idx) { $m.textContent = '索引加载中…';
    idx = await (await fetch('data/search-index.json')).json();
    $m.textContent = ''; }
}
function search(q) {
  const hits = [];
  outer: for (const ch of idx.chapters) {
    for (const [n, text] of ch.p) {
      if (text.includes(q)) {
        hits.push({i: ch.i, t: ch.t, n, text});
        if (hits.length >= 200) break outer;
      }
    }
  }
  return hits;
}
function render(q) {
  if (!q) { $r.innerHTML=''; $m.textContent=''; return; }
  const hits = search(q);
  $m.textContent = `共 ${hits.length} 处命中` + (hits.length>=200 ? '（仅显示前200条）' : '');
  const re = new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g');
  $r.innerHTML = hits.map(h => {
    const pos = h.text.indexOf(q);
    const snip = h.text.slice(Math.max(0, pos-40), pos+q.length+60);
    return `<div class="hit"><a class="loc" href="chapters/${h.i}.html#p${h.n}">${esc(h.t)} · 段${h.n}</a>
      <p>…${esc(snip).replace(re, m => `<mark>${m}</mark>`)}…</p></div>`;
  }).join('');
}
let timer;
$q.addEventListener('input', async () => {
  clearTimeout(timer);
  const q = $q.value.trim();
  timer = setTimeout(async () => { await ensure(); render(q); }, 150);
});
(async () => {
  const q = new URLSearchParams(location.search).get('q');
  if (q) { $q.value = q; await ensure(); render(q); }
})();
