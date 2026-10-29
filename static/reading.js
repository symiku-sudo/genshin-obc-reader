'use strict';
let readingAnchors = store.get('anchors', {}), lastReading = store.get('last-reading', null);
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
function rememberAnchor() {
  if (!current || window.readingLayoutPending) return;
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
  lastReading = {id:current.id,title:current.title}; store.set('last-reading',lastReading); renderResume();
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
  $('resume-reading').hidden=!lastReading;
  if(lastReading) $('resume-reading').textContent='继续阅读 · '+lastReading.title;
}
$('resume-reading').onclick=()=>{if(lastReading){activeTerms=[];navigate('#entry/'+lastReading.id);}};
renderResume();
let layoutTimer, layoutReleaseTimer;
window.addEventListener('resize',()=>{
  if(!current) return;
  const id=current.id;
  window.readingLayoutPending=true; clearTimeout(layoutTimer); clearTimeout(layoutReleaseTimer);
  layoutTimer=setTimeout(()=>{
    if(current?.id===id) restoreReadingAnchor(id);
    // Ignore the scroll event caused by restoration before accepting user scrolls.
    layoutReleaseTimer=setTimeout(()=>{window.readingLayoutPending=false;},220);
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
  const note={id:crypto.randomUUID ? crypto.randomUUID() : Date.now()+'-'+Math.random().toString(16).slice(2),entry:current.id,title:current.title,parts,created:Date.now()};
  const duplicate=highlights.some(h=>h.entry===note.entry&&JSON.stringify(h.parts)===JSON.stringify(parts));
  const next=duplicate?highlights:[...highlights,note];
  try {localStorage.setItem('obc-highlights',JSON.stringify(next));}
  catch { $('highlight-status').textContent='保存失败，请先备份并释放存储空间。';return; }
  highlights=next;window.getSelection().removeAllRanges();selectionParts=[];$('selection-tools').hidden=true;applyHighlights();
};
function applyHighlights() {
  if(!current)return;
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
}
function renderHighlights(){
  $('highlights-list').replaceChildren();$('highlights-status').textContent=highlights.length ? highlights.length+' 条划线' : '暂无划线。阅读时长按选择正文，再点“划线”。';
  for(const note of [...highlights].reverse()){
    const card=document.createElement('section');card.className='highlight-card';
    const title=document.createElement('h3');title.textContent=note.title;
    const quote=document.createElement('blockquote');quote.textContent=note.parts.map(p=>p.quote).join('\n');
    const open=document.createElement('button');open.textContent='查看原文';
    open.onclick=async()=>{
      $('highlights-dialog').close();activeTerms=[];navigate('#entry/'+note.entry);
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
    card.append(title,quote,open,remove);$('highlights-list').append(card);
  }
}
$('open-highlights').onclick=()=>{renderHighlights();$('highlights-dialog').showModal();};
$('close-highlights').onclick=()=>$('highlights-dialog').close();
