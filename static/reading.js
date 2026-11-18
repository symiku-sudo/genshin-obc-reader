'use strict';
let readingAnchors = store.get('anchors', {}), lastReading = store.get('last-reading', null);
let recentReadings = store.get('recent-readings', lastReading ? [lastReading] : []).slice(0,2);
let editingNote = null;
let highlights = store.get('highlights', []), selectionParts = [];
const prose = () => [...$('article').querySelectorAll('section > p:not(.section-meta)')];
function paragraphKey(p) {
  return {section:p.parentElement.id, paragraph:[...p.parentElement.querySelectorAll(':scope > p:not(.section-meta)')].indexOf(p)};
}
function anchorParagraph(a) {
  const section = $(a.section);
  return section && $('article').contains(section) ? section.querySelectorAll(':scope > p:not(.section-meta)')[a.paragraph] : null;
}
function textPoint(p, offset) {
  const walker = document.createTreeWalker(p, NodeFilter.SHOW_TEXT);
  let n; while ((n = walker.nextNode())) { if (offset <= n.length) return [n, offset]; offset -= n.length; }
  return [p, p.childNodes.length];
}
function characterRange(p, start, end = start + 1) {
  const range = document.createRange(), a = textPoint(p, start), b = textPoint(p, Math.min(end, p.textContent.length));
  range.setStart(...a); range.setEnd(...b); return range;
}
function readingTop() { return document.querySelector('.reader-nav').offsetHeight + 12; }
let readingViewport = {width:window.innerWidth,height:window.innerHeight};
function readingLayoutChanged() {
  return window.readingLayoutPending || window.innerWidth!==readingViewport.width || window.innerHeight!==readingViewport.height;
}
function rememberAnchor() {
  if (!current || readingLayoutChanged()) return;
  const top = readingTop(), paragraphs = prose();
  const p = paragraphs.find(p => p.getBoundingClientRect().bottom > top);
  if (p) {
    let offset = 0;
    // Range rectangles identify the visible line independently of screen width.
    if (typeof document.createRange().getBoundingClientRect === 'function') {
      let low = 0, high = Math.max(0,p.textContent.length-1);
      while (low < high) {
        const mid = Math.floor((low+high)/2);
        if (characterRange(p,mid).getBoundingClientRect().bottom <= top) low=mid+1; else high=mid;
      }
      offset=low;
    }
    const rect = typeof document.createRange().getBoundingClientRect === 'function' ? characterRange(p,offset).getBoundingClientRect() : p.getBoundingClientRect();
    readingAnchors[current.id] = {...paragraphKey(p), offset, top:rect.top-top, quote:p.textContent.slice(offset,offset+32)};
    store.set('anchors',readingAnchors);
  }
  lastReading = {id:current.id,title:current.title}; store.set('last-reading',lastReading);
  recentReadings=[lastReading,...recentReadings.filter(x=>x.id!==current.id)].slice(0,2);store.set('recent-readings',recentReadings);renderResume();
}
function restoreReadingAnchor(id, explicit) {
  const a = explicit || readingAnchors[id]; if (!a) return false;
  const p = anchorParagraph(a); if (!p) return false;
  let offset = a.offset;
  if (a.quote && p.textContent.slice(offset,offset+a.quote.length)!==a.quote) {
    offset=p.textContent.indexOf(a.quote); if(offset<0) return false;
  }
  if (typeof document.createRange().getBoundingClientRect !== 'function') {p.scrollIntoView();return true;}
  const rect=characterRange(p,offset).getBoundingClientRect();
  window.scrollTo(0,Math.max(0,window.scrollY+rect.top-readingTop()-(a.top||0)));return true;
}
function renderResume() {
  ['resume-reading','resume-reading-second'].forEach((id,index)=>{
    const item=recentReadings[index];$(id).hidden=!item;
    if(item){$(id).textContent='继续阅读 · '+item.title;$(id).onclick=()=>{activeTerms=[];navigate('#entry/'+item.id);};}
  });
}
renderResume();
let layoutTimer, layoutReleaseTimer;
window.addEventListener('resize',()=>{
  if(!current) {readingViewport={width:window.innerWidth,height:window.innerHeight};return;}
  const id=current.id;
  window.readingLayoutPending=true; clearTimeout(layoutTimer); clearTimeout(layoutReleaseTimer);
  layoutTimer=setTimeout(()=>{
    if(current?.id===id) restoreReadingAnchor(id);
    // Ignore the scroll event caused by restoration before accepting user scrolls.
    layoutReleaseTimer=setTimeout(()=>{readingViewport={width:window.innerWidth,height:window.innerHeight};window.readingLayoutPending=false;},220);
  },160);
});
function clearReadingSelection() {
  window.getSelection().removeAllRanges();selectionParts=[];$('selection-tools').hidden=true;
}
function selectedParts() {
  const selection=window.getSelection();
  if(!current || !selection.rangeCount || selection.isCollapsed) return [];
  const selected=selection.getRangeAt(0);
  if(!$('article').contains(selected.startContainer)||!$('article').contains(selected.endContainer))return [];
  return prose().filter(p=>selected.intersectsNode(p)).map(p=>{
    const before=document.createRange();before.selectNodeContents(p);
    let start=0,end=p.textContent.length;
    if(p.contains(selected.startContainer)){before.setEnd(selected.startContainer,selected.startOffset);start=before.toString().length;}
    if(p.contains(selected.endContainer)){before.selectNodeContents(p);before.setEnd(selected.endContainer,selected.endOffset);end=before.toString().length;}
    return {...paragraphKey(p),start,end,quote:p.textContent.slice(start,end)};
  }).filter(p=>p.quote.trim());
}
document.addEventListener('selectionchange',()=>{
  selectionParts=selectedParts(); $('selection-tools').hidden=!selectionParts.length;
  $('highlight-status').textContent='';
});
$('save-highlight').addEventListener('pointerdown',e=>e.preventDefault());
$('save-highlight').onclick=()=>{
  if(!current || !selectionParts.length)return;
  const parts=selectionParts;
  const note={id:crypto.randomUUID ? crypto.randomUUID() : Date.now()+'-'+Math.random().toString(16).slice(2),entry:current.id,title:current.title,category:current.category,parts,created:Date.now()};
  const duplicate=highlights.some(h=>h.entry===note.entry&&JSON.stringify(h.parts)===JSON.stringify(parts));
  const next=duplicate?highlights:[...highlights,note];
  try {localStorage.setItem('obc-highlights',JSON.stringify(next));}
  catch { $('highlight-status').textContent='保存失败，请先备份并释放存储空间。';return; }
  highlights=next;window.getSelection().removeAllRanges();selectionParts=[];$('selection-tools').hidden=true;applyHighlights();
};
function applyHighlights() {
  if(!current)return;
  for(const badge of $('article').querySelectorAll('.note-badge'))badge.remove();
  // Unwrap only personal marks; search highlights remain untouched.
  for(const mark of $('article').querySelectorAll('mark.user-highlight'))mark.replaceWith(...mark.childNodes);
  $('article').normalize();
  const ranges=new Map();
  for(const note of highlights.filter(h=>h.entry===current.id))for(const part of note.parts){
    const p=anchorParagraph(part);if(!p||p.textContent.slice(part.start,part.end)!==part.quote)continue;
    if(!ranges.has(p))ranges.set(p,[]);ranges.get(p).push([part.start,part.end]);
  }
  for(const [p,spans] of ranges){
    spans.sort((a,b)=>a[0]-b[0]);const merged=[];
    for(const span of spans){const previous=merged.at(-1);if(previous&&span[0]<=previous[1])previous[1]=Math.max(previous[1],span[1]);else merged.push([...span]);}
    const nodes=[],walker=document.createTreeWalker(p,NodeFilter.SHOW_TEXT);let node,offset=0;
    while((node=walker.nextNode())){nodes.push({node,start:offset,end:offset+node.length});offset+=node.length;}
    for(const item of nodes.reverse())for(const [start,end] of [...merged].reverse()){
      const a=Math.max(start,item.start)-item.start,b=Math.min(end,item.end)-item.start;if(b<=a)continue;
      const range=document.createRange();range.setStart(item.node,a);range.setEnd(item.node,b);
      const mark=document.createElement('mark');mark.className='user-highlight';range.surroundContents(mark);
    }
  }
  // Empty buttons add no characters to source text, selections or saved anchors.
  for(const note of highlights.filter(h=>h.entry===current.id && h.note?.trim())){
    const part=note.parts.at(-1),p=anchorParagraph(part);
    if(!p || p.textContent.slice(part.start,part.end)!==part.quote)continue;
    const badge=document.createElement('button');badge.type='button';badge.className='note-badge';
    badge.dataset.noteId=note.id;badge.setAttribute('aria-label','查看划线笔记');badge.title='查看划线笔记';
    const range=characterRange(p,part.end,part.end);range.insertNode(badge);
  }
}

let highlightScroll = 0, highlightLimit = 50, highlightOrigin = '', highlightReaderReturn = false;
let highlightSources = new Map(), highlightSourceRequest = 0;
const highlightCategory = note => highlightSources.get(String(note.entry))?.category || (typeof note.category==='string'&&note.category) || '未分类';
function rememberHighlights() {
  if (!$('highlights-page').hidden) highlightScroll = window.scrollY;
}
async function loadHighlightSources() {
  const ticket = ++highlightSourceRequest;
  try {
    const result = await api('/api/entry-metadata');
    if(ticket !== highlightSourceRequest)return;
    highlightSources = new Map(result.items.map(x=>[String(x.id),x]));
    $('highlight-source-status').textContent='';renderHighlights();
  } catch {
    if(ticket === highlightSourceRequest)$('highlight-source-status').textContent='部分旧划线的分类暂时无法读取，可重新打开本页重试；划线和笔记仍可搜索。';
  }
}
function showHighlights() {
  $('library').hidden=true;$('reader').hidden=true;$('highlights-page').hidden=false;
  $('selection-return').hidden=true;document.body.classList.remove('has-selection-return');
  renderHighlights();window.scrollTo(0,highlightScroll);loadHighlightSources();
}
function renderHighlights(){
  const scroll = $('highlights-page').hidden ? highlightScroll : window.scrollY;
  const category=$('highlight-category').value;
  const categories=[...new Set(highlights.map(highlightCategory))].sort((a,b)=>a.localeCompare(b,'zh-CN'));
  if(category&&!categories.includes(category))categories.push(category);
  $('highlight-category').replaceChildren(new Option('全部分类',''),...categories.map(c=>new Option(c,c)));
  $('highlight-category').value=category;
  const keyword=$('highlight-query').value.trim().toLocaleLowerCase();
  const matches=highlights.filter(note=>(!category||highlightCategory(note)===category)&&(!keyword||[note.title,highlightSources.get(String(note.entry))?.title,note.note,...note.parts.map(p=>p.quote)].join('\n').toLocaleLowerCase().includes(keyword))).sort((a,b)=>b.created-a.created);
  $('highlights-list').replaceChildren();
  $('highlights-status').textContent=!highlights.length?'暂无划线。阅读时长按选择正文，再点“划线”。':!matches.length?'没有匹配的划线，试试更换关键词或分类。':`共 ${highlights.length} 条 · 匹配 ${matches.length} 条 · 最新在前`;
  $('highlights-more').hidden=matches.length<=highlightLimit;
  for(const note of matches.slice(0,highlightLimit)){
    const card=document.createElement('section');card.className='highlight-card';
    const title=document.createElement('h3');title.textContent=note.title;
    const categoryLabel=document.createElement('p');categoryLabel.className='section-meta';categoryLabel.textContent=highlightCategory(note);
    const quote=document.createElement('blockquote');quote.textContent=note.parts.map(p=>p.quote).join('\n');
    const open=document.createElement('button');open.textContent='查看原文';
    open.onclick=async()=>{
      rememberHighlights();highlightReaderReturn=true;activeTerms=[];navigate('#entry/'+note.entry);
      const ticket=routeId;
      for(let tries=0;tries<100;tries++){
        await new Promise(r=>setTimeout(r,50));if(ticket!==routeId)return;
        if(current?.id===note.entry){
          const part=note.parts[0];const a={...part,offset:part.start,top:0};
          if(!restoreReadingAnchor(note.entry,a)){$('reader-tools').open=true;$('reader-status').textContent='正文已变化，原划线保留在划线列表中。';}
          remember();return;
        }
      }
    };
    const remove=document.createElement('button');remove.textContent='删除';
    remove.onclick=()=>{
      const next=highlights.filter(h=>h.id!==note.id);
      try{localStorage.setItem('obc-highlights',JSON.stringify(next));}catch{$('highlights-status').textContent='删除未保存，请重试。';return;}
      highlights=next;applyHighlights();renderHighlights();
    };
    const noteText=document.createElement('p');noteText.className='highlight-note';noteText.textContent=note.note||'';noteText.hidden=!note.note;
    const edit=document.createElement('button');edit.textContent=note.note?'编辑笔记':'添加笔记';edit.onclick=()=>openNoteEditor(note);
    const source=document.createElement('div');source.className='highlight-source';source.append(title,categoryLabel);
    const actions=document.createElement('div');actions.className='highlight-actions';
    const more=document.createElement('details');more.className='highlight-more';
    const summary=document.createElement('summary');summary.textContent='⋯';summary.setAttribute('aria-label','更多划线操作');
    const menu=document.createElement('div');menu.className='highlight-menu';menu.append(edit,remove);remove.className='danger-button';
    more.append(summary,menu);actions.append(open,more);
    card.append(quote,noteText,source,actions);$('highlights-list').append(card);
  }
  if(!$('highlights-page').hidden)window.scrollTo(0,scroll);
}
$('open-highlights').onclick=()=>{
  if(location.hash==='#highlights')return;
  highlightOrigin=location.hash;highlightReaderReturn=false;navigate('#highlights');
};
$('close-highlights').onclick=()=>{highlightReaderReturn=false;navigate(highlightOrigin==='#highlights'?'':highlightOrigin);};
function filterHighlights(){highlightLimit=50;highlightScroll=0;window.scrollTo(0,0);renderHighlights();}
$('highlight-query').oninput=filterHighlights;
$('highlight-category').onchange=filterHighlights;
$('highlights-more').onclick=()=>{highlightLimit+=50;renderHighlights();};
window.addEventListener('scroll',rememberHighlights,{passive:true});

function openNoteEditor(note) {
  editingNote=note;$('delete-note').hidden=!highlights.some(h=>h.id===note.id);$('note-quote').textContent=note.parts.map(p=>p.quote).join('\n');$('note-text').value=note.note||'';$('note-status').textContent='';$('note-editor').showModal();
}
$('annotate-selection').addEventListener('pointerdown',e=>e.preventDefault());
$('annotate-selection').onclick=()=>{
  if(!current||!selectionParts.length)return;
  const parts=selectionParts.map(p=>({...p}));
  const existing=highlights.find(h=>h.entry===current.id&&JSON.stringify(h.parts)===JSON.stringify(parts));
  const note=existing||{id:crypto.randomUUID?crypto.randomUUID():Date.now()+'-'+Math.random(),entry:current.id,title:current.title,category:current.category,parts,created:Date.now()};
  clearReadingSelection();openNoteEditor(note);
};
$('save-note').onclick=()=>{
  if(!editingNote)return;
  const updated={...editingNote,note:$('note-text').value,modified:Date.now()};
  const next=highlights.some(h=>h.id===updated.id)?highlights.map(h=>h.id===updated.id?updated:h):[...highlights,updated];
  try{localStorage.setItem('obc-highlights',JSON.stringify(next));}catch{$('note-status').textContent='笔记未保存，请释放存储空间后重试。';return;}
  highlights=next;applyHighlights();renderHighlights();$('note-editor').close();editingNote=null;
};
$('delete-note').onclick=()=>{
  if(!editingNote)return;
  const note=highlights.find(h=>h.id===editingNote.id);if(!note)return;
  if(note.note?.trim() && !window.confirm('删除这条划线及其笔记？'))return;
  const next=highlights.filter(h=>h.id!==note.id);
  try{localStorage.setItem('obc-highlights',JSON.stringify(next));}catch{$('note-status').textContent='删除未保存，请重试。';return;}
  highlights=next;clearReadingSelection();applyHighlights();renderHighlights();$('note-editor').close();editingNote=null;
};
$('cancel-note').onclick=()=>{$('note-editor').close();editingNote=null;};
$('article').addEventListener('click',event=>{
  const badge=event.target.closest('.note-badge');
  if(badge){const note=highlights.find(h=>h.id===badge.dataset.noteId);if(note)openNoteEditor(note);return;}
  const mark=event.target.closest('mark.user-highlight');if(!mark||!window.getSelection().isCollapsed)return;
  const p=mark.closest('p'),key=paragraphKey(p);const range=document.createRange();range.selectNodeContents(p);range.setEndBefore(mark);const offset=range.toString().length;
  const note=highlights.find(h=>h.entry===current.id&&h.parts.some(a=>a.section===key.section&&a.paragraph===key.paragraph&&a.start<=offset&&a.end>offset));
  if(note)openNoteEditor(note);
});

window.readingReady=true;
