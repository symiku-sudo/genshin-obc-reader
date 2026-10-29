'use strict';
const $ = id => document.getElementById(id);
const store = {
  get(key, fallback) { try { return JSON.parse(localStorage.getItem('obc-' + key)) ?? fallback; } catch { return fallback; } },
  set(key, value) { try { localStorage.setItem('obc-' + key, JSON.stringify(value)); } catch {} }
};
let bookmarks = store.get('bookmarks', []), positions = store.get('positions', {});
let fontSize = store.get('font', 18), current = null, requestId = 0, routeId = 0, timer;
let viewMode = 'browse';
let listScroll = 0, remotePage = 1, remoteQuery = '', remoteMode = false;
let listQuery = '', activeTerms = [], lastItems = [], localPage = 1, localTotal = 0;
if (![16,18,20,22,24].includes(fontSize)) fontSize = 18;
// Bound memory use and revalidate after one minute for background imports.
const entryCache = new Map();
function cacheEntry(entry) {
  const id = String(entry.id);
  entryCache.delete(id);
  entryCache.set(id, {entry, at: Date.now()});
  while (entryCache.size > 24) entryCache.delete(entryCache.keys().next().value);
  return entry;
}
async function readEntry(id) {
  const cached = entryCache.get(id);
  if (cached && Date.now() - cached.at < 60000) return cached.entry;
  return cacheEntry(await api('/api/entry/' + id));
}
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function highlighted(text, terms = activeTerms) {
  if (!terms.length) return esc(text);
  const pattern = terms.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|');
  const rx = new RegExp(pattern, 'gi'); let last = 0, out = '';
  for (const match of String(text).matchAll(rx)) { out += esc(String(text).slice(last, match.index)) + '<mark>' + esc(match[0]) + '</mark>'; last = match.index + match[0].length; }
  return out + esc(String(text).slice(last));
}
async function api(path, options) {
  const r = await fetch(path, options); const data = await r.json();
  if (!r.ok) { const e = new Error(data.error || '请求失败'); e.status = r.status; throw e; }
  return data;
}
async function updateStats() {
  const s = await api('/api/stats');
  $('stats').textContent = `已缓存 ${s.entries} 个词条 · ${s.sections} 段中文文本`;
  const selected = $('category').value;
  $('category').replaceChildren(new Option('全部分类', ''), ...s.categories.map(c => new Option(c, c)));
  $('category').value = selected;
  const selectedType = $('text-type').value;
  $('text-type').replaceChildren(new Option('全部文本', ''), ...s.text_types.map(t => new Option(t, t)));
  $('text-type').value = selectedType;
}
function renderCards(items, total) {
  lastItems = items;
  const visible = remoteMode && $('favorites').checked ? items.filter(x => bookmarks.includes(x.id)) : items;
  $('count').textContent = `${visible.length} 个结果 / 共 ${total} 个`;
  function href(x, hit) { return '#entry/' + encodeURIComponent(x.id) + (hit?.section_id ? '/' + hit.section_id : '') + (Number.isInteger(hit?.paragraph_index) ? '/p' + hit.paragraph_index : ''); }
  $('results').innerHTML = visible.length ? visible.map(x => {
    const matches = x.matches || [], hit = activeTerms.length ? (matches[0] || x) : null;
    const extra = activeTerms.length && matches.length > 1 ? `<details class="hit-list"><summary>展开更多命中片段（本页展示 ${matches.length} 个）</summary>${matches.slice(1).map(h => `<a class="hit" href="${href(x,h)}"><span class="section-label">${esc(h.section_title)}</span><p>${highlighted(h.snippet)}</p></a>`).join('')}${x.match_count>12 ? '<p>还有更多命中，可进入词条查看原文。</p>' : ''}</details>` : '';
    return `<div class="card${x.is_read ? ' is-read' : ''}"><a class="card-main" href="${href(x,hit)}"><span class="cat">${esc(x.category)}${x.text_type ? ' · ' + esc(x.text_type) : ''}${bookmarks.includes(x.id) ? ' · 已收藏' : ''}</span><h3>${highlighted(x.title)}</h3>${activeTerms.length && x.section_title ? `<span class="section-label">${esc(x.section_title)}</span>` : ''}${activeTerms.length && x.snippet ? `<p>${highlighted(x.snippet)}</p>` : remoteMode ? '<p>打开并加入文本库</p>' : ''}</a>${extra}${!remoteMode ? `<div class="card-foot"><span>${x.is_read ? '已读' : '未读'}</span><button class="read-toggle" data-read-id="${esc(x.id)}" aria-pressed="${Boolean(x.is_read)}">${x.is_read ? '标为未读' : '标为已读'}</button></div>` : ''}</div>`;
  }).join('') : '<p class="empty">没有匹配结果。可以缩短关键词，调整分类，或导入更多文本。</p>';
}
async function localSearch(reset = true) {
  const id = ++requestId;
  if (reset) localPage = 1;
  remoteMode = false; $('more').hidden = true; $('local-pager').hidden = false;
  listQuery = viewMode === 'search' ? $('query').value.trim() : '';
  activeTerms = $('match-mode').value === 'phrase' ? (listQuery ? [listQuery] : []) : [...new Set(listQuery.split(/\s+/).filter(Boolean))];
  $('results-title').textContent = listQuery ? '正文搜索结果' : (viewMode === 'browse' ? '自由浏览' : '全部文本');
  $('status').textContent = '正在搜索本地资料…';
  try {
    let url = '/api/search?q=' + encodeURIComponent(listQuery) + '&category=' + encodeURIComponent($('category').value) + '&type=' + encodeURIComponent($('text-type').value) + '&mode=' + $('match-mode').value + '&page=' + localPage + '&read=' + $('read-filter').value;
    if ($('favorites').checked) url += '&favorite_only=1&favorites=' + encodeURIComponent(bookmarks.join(','));
    const data = await api(url);
    if (id !== requestId) return;
    localTotal = data.total;
    const lastPage = Math.max(1, Math.ceil(data.total / data.page_size));
    if (localPage > lastPage) { localPage = lastPage; return localSearch(false); }
    renderCards(data.items, data.total);
    const pages = Math.max(1, Math.ceil(data.total / data.page_size));
    $('local-page').textContent = `${localPage} / ${pages}`;
    $('local-prev').disabled = localPage <= 1; $('local-next').disabled = localPage >= pages;
    $('status').textContent = listQuery ? ($('match-mode').value === 'phrase' ? '按完整原文短语匹配；空格也属于短语。' : '范围：已缓存中文文本；多个词需匹配同一段文本。') : '';
  } catch (e) { if (id === requestId) $('status').textContent = '搜索失败：' + e.message; }
}
async function onlineSearch(next = false) {
  clearTimeout(timer);
  const q = next ? remoteQuery : $('remote-query').value.trim();
  if (!q) { $('status').textContent = '先输入需要在线查找的词条名称。'; return; }
  $('management').close();
  if (!$('reader').hidden) {
    remember(); ++routeId; current = null;
    history.pushState(null, '', location.pathname);
    $('reader').hidden = true; $('library').hidden = false;
  }
  const id = ++requestId; remoteMode = true; $('local-pager').hidden = true;
  remotePage = next ? remotePage + 1 : 1; remoteQuery = q;
  activeTerms = [...new Set(q.split(/\s+/).filter(Boolean))];
  $('status').textContent = '正在查询观测枢…'; $('results-title').textContent = '在线词条结果'; $('more').hidden = true;
  $('results').replaceChildren();
  try {
    const data = await api('/api/remote?q=' + encodeURIComponent(q) + '&page=' + remotePage);
    if (id !== requestId) return;
    renderCards(data.items, data.items.length);
    $('status').textContent = `在线第 ${remotePage} 页 · 由原站搜索返回，分类、文本与阅读状态筛选仅用于本地搜索。点开词条将缓存正文。`;
    $('more').hidden = data.items.length < 20;
  } catch (e) { if (id === requestId) { $('status').textContent = e.message; if(next) remotePage--; } }
}
function remember() {
  if (current && !window.readingLayoutPending) { positions[current.id] = window.scrollY; store.set('positions', positions); if (typeof rememberAnchor === 'function') rememberAnchor(); }
}
function setBookmark() {
  $('bookmark').textContent = current && bookmarks.includes(current.id) ? '已收藏 ★' : '收藏 ☆';
}
function paintEntry(entry, target, paragraphIndex, readMs) {
  const renderStart = performance.now();
  current = entry;
  $('reader-title').textContent = entry.title;
  $('reader-category').textContent = entry.category;
  $('source').href = entry.source;
  $('updated').textContent = (entry.snapshot ? '样本采集于 ' : '缓存于 ') + new Date(entry.fetched_at).toLocaleString('zh-CN');
  $('warnings').textContent = entry.warnings.join('；');
  $('toc-links').replaceChildren(...entry.sections.map(s => {
    const a = document.createElement('a'); a.textContent = (s.context ? s.context + ' · ' : '') + s.title; a.href = '#';
    a.onclick = e => { e.preventDefault(); $(s.id).scrollIntoView({behavior:'smooth'}); };
    return a;
  }));
  $('article').className = 'size-' + fontSize;
  // Extracted prose consists of plain-text paragraphs. Highlight before insertion,
  // avoiding a second walk and replacement of every matching DOM text node.
  $('article').innerHTML = entry.sections.map(s => {
    const body = activeTerms.length ? s.text.split(/\r?\n/).filter(line => line.trim()).map(line => '<p>' + highlighted(line) + '</p>').join('') : s.html;
    return `<section id="${esc(s.id)}"><p class="section-meta">${esc([s.tab, s.context, s.text_type].filter(Boolean).join(' · '))}</p><h2>${highlighted(s.title)}</h2>${body}</section>`;
  }).join('');
  if (typeof applyHighlights === 'function') applyHighlights();
  setBookmark(); setReadButton(); $('reader-status').textContent = entry.requires_refresh ? '请更新此词条的缓存。' : '已保存中文原文，可断网阅读；不包含图片、音频和属性表。';
  requestAnimationFrame(() => {
    if (current !== entry) return;
    if (target && $(target)) {
      const paragraphs = $(target).querySelectorAll(':scope > p:not(.section-meta)');
      const focus = paragraphIndex !== undefined ? paragraphs[Number(paragraphIndex)] : null;
      (focus || $(target)).scrollIntoView();
    }
    else if (typeof restoreReadingAnchor !== 'function' || !restoreReadingAnchor(entry.id)) window.scrollTo(0, positions[entry.id] || 0);
    if (typeof rememberAnchor === 'function') rememberAnchor();
    if (readMs !== undefined) $('reader-status').textContent += ` 读取 ${Math.round(readMs)} ms · 正文准备 ${Math.round(performance.now() - renderStart)} ms。`;
  });
}
async function route() {
  if (current && typeof clearReadingSelection === 'function') clearReadingSelection();
  const ticket = ++routeId;
  const match = location.hash.match(/^#entry\/(\d{1,12})(?:\/(section-\d+(?:-\d+){0,2})(?:\/p(\d+))?)?$/);
  remember(); current = null;
  if (!match) {
    $('reader').hidden = true; $('library').hidden = false;
    if (!remoteMode && !lastItems.length) await localSearch(false); else renderCards(lastItems, remoteMode ? lastItems.length : localTotal);
    if (ticket === routeId) window.scrollTo(0, listScroll);
    return;
  }
  if (!$('library').hidden) listScroll = window.scrollY;
  $('library').hidden = true; $('reader').hidden = false;
  $('reader-title').textContent = '读取词条…'; $('reader-category').textContent = '';
  $('article').replaceChildren(); $('toc-links').replaceChildren(); $('warnings').textContent = '';
  $('updated').textContent = ''; $('source').removeAttribute('href');
  $('reader-tools').open = false; $('mark-read').disabled = true;
  $('reader-status').textContent = '优先读取本地缓存；未缓存时从观测枢获取。'; window.scrollTo(0, 0);
  try {
    let entry; const readStart = performance.now();
    try { entry = await readEntry(match[1]); }
    catch(e) {
      if(e.status !== 404) throw e;
      if (ticket !== routeId) return;
      $('reader-status').textContent = '此词条尚未缓存，正在从观测枢下载…';
      entry = cacheEntry(await api('/api/import', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:match[1]})}));
      updateStats().catch(() => {});
    }
    if (ticket !== routeId) return;
    paintEntry(entry, match[2], match[3], performance.now() - readStart);
  } catch(e) { if (ticket === routeId) { $('reader-tools').open = true; $('reader-title').textContent = '暂时无法读取'; $('reader-status').textContent = e.message; } }
}
function switchView(mode) {
  clearTimeout(timer);
  viewMode = mode;
  $('browse-view').setAttribute('aria-pressed', String(mode === 'browse'));
  $('search-view').setAttribute('aria-pressed', String(mode === 'search'));
  $('search-form').hidden = mode !== 'search';
  localSearch();
  if (mode === 'search') $('query').focus();
}
$('browse-view').onclick = () => switchView('browse');
$('search-view').onclick = () => switchView('search');
$('read-filter').onchange = () => localSearch();
$('open-management').onclick = () => {
  $('management').showModal();
  refreshLibrary().catch(e => { $('import-status').textContent = e.message; });
};
$('close-management').onclick = () => $('management').close();
function setReadButton() {
  $('mark-read').disabled = !current;
  $('mark-read').textContent = current?.is_read ? '已读 ✓ · 标为未读' : '标为已读';
  $('mark-read').setAttribute('aria-pressed', String(Boolean(current?.is_read)));
}
async function toggleRead(id, value, button) {
  button.disabled = true;
  $('read-feedback').textContent = '';
  try {
    const result = await api('/api/read', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,is_read:value})});
    if (entryCache.has(id)) entryCache.get(id).entry.is_read = result.is_read;
    const item = lastItems.find(x => x.id === id); if (item) item.is_read = result.is_read;
    if (current?.id === id) { current.is_read = result.is_read; setReadButton(); }
    // Keep this result snapshot until the user explicitly searches, filters or pages again.
    for (const control of $('results').querySelectorAll('[data-read-id]')) {
      if (control.dataset.readId !== id) continue;
      control.setAttribute('aria-pressed', String(result.is_read));
      control.textContent = result.is_read ? '标为未读' : '标为已读';
      control.closest('.card').classList.toggle('is-read', result.is_read);
      control.previousElementSibling.textContent = result.is_read ? '已读' : '未读';
    }
  } catch(e) {
    if (current?.id === id) { $('reader-tools').open = true; $('reader-status').textContent = '阅读状态保存失败：' + e.message; }
    else $('read-feedback').textContent = '阅读状态保存失败：' + e.message;
  } finally { button.disabled = false; }
}
$('mark-read').onclick = () => { if (current) toggleRead(current.id, !current.is_read, $('mark-read')); };
$('results').addEventListener('click', e => {
  const button = e.target.closest('[data-read-id]');
  if (!button) return;
  const item = lastItems.find(x => x.id === button.dataset.readId);
  if (item) toggleRead(item.id, !item.is_read, button);
});
$('search-form').onsubmit = e => { e.preventDefault(); clearTimeout(timer); localSearch(); };
$('query').oninput = () => { clearTimeout(timer); timer = setTimeout(localSearch, 180); };
$('category').onchange = () => localSearch();
$('text-type').onchange = () => localSearch();
$('match-mode').onchange = () => localSearch();
$('local-prev').onclick = () => { if(localPage>1){localPage--;localSearch(false);} };
$('local-next').onclick = () => { if(localPage*20<localTotal){localPage++;localSearch(false);} };
$('favorites').onchange = () => remoteMode ? renderCards(lastItems, lastItems.length) : localSearch();
$('remote').onclick = () => onlineSearch(); $('more').onclick = () => onlineSearch(true);
$('back').onclick = () => navigate('');
$('bookmark').onclick = () => {
  if (!current) return;
  bookmarks = bookmarks.includes(current.id) ? bookmarks.filter(x => x !== current.id) : [...bookmarks, current.id];
  store.set('bookmarks', bookmarks); setBookmark();
};
function resize(delta) { remember(); fontSize = Math.min(24, Math.max(16, fontSize + delta)); store.set('font', fontSize); $('article').className = 'size-' + fontSize; if (current && typeof restoreReadingAnchor === 'function') restoreReadingAnchor(current.id); }
$('smaller').onclick = () => resize(-2); $('larger').onclick = () => resize(2);
$('refresh').onclick = async () => {
  if (!current) return;
  const id = current.id, ticket = routeId; remember(); $('refresh').disabled = true; $('reader-status').textContent = '正在更新…';
  try {
    const entry = await api('/api/import', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,refresh:true})});
    cacheEntry(entry);
    if (routeId === ticket) paintEntry(entry);
  } catch(e) { if (routeId === ticket) $('reader-status').textContent = e.message; }
  finally { $('refresh').disabled = false; }
};
let scrollTimer;
window.addEventListener('scroll', () => { clearTimeout(scrollTimer); scrollTimer = setTimeout(remember, 120); }, {passive:true});
window.addEventListener('pagehide', remember);
function navigate(hash) {
  remember();
  history.pushState(null, '', location.pathname + location.search + hash);
  route();
}
history.scrollRestoration = 'manual';
document.addEventListener('click', e => {
  const a = e.target.closest('a');
  if (!a || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey || e.button !== 0) return;
  const href = a.getAttribute('href');
  if (href && /^#entry\/\d/.test(href)) { e.preventDefault(); navigate(href); }
  else if (a.classList.contains('brand')) { e.preventDefault(); navigate(''); }
});
window.addEventListener('popstate', route);
async function loadSampleList() {
  const data = await api('/api/samples');
  $('sample-list').replaceChildren(...data.items.map(item => {
    const button = document.createElement('button');
    button.textContent = item.category + ' · ' + item.title;
    button.onclick = async () => {
      button.disabled = true; $('sample-status').textContent = '正在载入中文样本…';
      try {
        entryCache.delete(String(item.id));
        await api('/api/sample', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({id:item.id})});
        $('sample-status').textContent = ''; $('management').close(); activeTerms = []; navigate('#entry/' + item.id);
        updateStats().catch(() => {});
      } catch(e) { $('sample-status').textContent = e.message; }
      finally { button.disabled = false; }
    };
    return button;
  }));
}
let samplesLoaded = false;
$('samples').addEventListener('toggle', async () => {
  if (!$('samples').open || samplesLoaded) return;
  try { await loadSampleList(); samplesLoaded = true; }
  catch(e) { $('sample-status').textContent = e.message; }
});
updateStats().catch(e => { $('stats').textContent = '本地服务尚未连接。'; });
route();
