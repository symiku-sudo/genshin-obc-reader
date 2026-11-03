'use strict';
let selectionSource = null;
let searchKeywords = [], searchHistory = store.get('search-history', []);
const uniqueKeywords = terms => [...new Set(terms.map(t=>t.trim()).filter(Boolean))];
function getSearchKeywords() {
  const pending=$('match-mode').value==='phrase'?[$('query').value]:$('query').value.split(/\s+/);
  const terms=uniqueKeywords([...searchKeywords,...pending]);
  return $('match-mode').value==='phrase' && terms.length ? [terms.join(' ')] : terms;
}
function renderKeywords() {
  $('keyword-list').replaceChildren();
  const relation=$('match-mode').value==='all'?'且':'或';
  searchKeywords.forEach((word,index)=>{
    if(index){const join=document.createElement('span');join.textContent=relation;$('keyword-list').append(join);}
    const button=document.createElement('button');button.type='button';button.className='keyword';button.textContent=word+' ×';button.setAttribute('aria-label','删除关键词 '+word);
    button.onclick=()=>{searchKeywords.splice(index,1);renderKeywords();localSearch();};$('keyword-list').append(button);
  });
  $('add-keyword').hidden=$('match-mode').value==='phrase';
}
function saveSearchHistory() {
  const keywords=getSearchKeywords();if(!keywords.length)return;
  const mode=$('match-mode').value;
  const same=item=>item.mode===mode&&JSON.stringify(item.keywords)===JSON.stringify(keywords);
  const next=[{keywords,mode},...searchHistory.filter(item=>!same(item))].slice(0,30);
  try{localStorage.setItem('obc-search-history',JSON.stringify(next));searchHistory=next;renderSearchHistory();}
  catch{$('status').textContent='搜索历史保存失败，搜索仍可使用。';}
}
function renderSearchHistory() {
  $('search-history-list').replaceChildren();
  $('clear-search-history').disabled=!searchHistory.length;
  for(const item of searchHistory){
    const row=document.createElement('div');row.className='history-row';
    const use=document.createElement('button');use.type='button';use.className='history-query';
    use.textContent=item.mode==='phrase'?'精确短语：'+item.keywords.join(' '):item.keywords.join(item.mode==='all'?' 且 ':' 或 ');
    use.onclick=()=>{clearTimeout(timer);searchKeywords=[...item.keywords];$('query').value='';$('match-mode').value=item.mode;renderKeywords();saveSearchHistory();localSearch();};
    const remove=document.createElement('button');remove.type='button';remove.textContent='删除';
    remove.onclick=()=>{const next=searchHistory.filter(x=>x!==item);try{localStorage.setItem('obc-search-history',JSON.stringify(next));searchHistory=next;renderSearchHistory();}catch{$('status').textContent='删除历史失败，请重试。';}};
    row.append(use,remove);$('search-history-list').append(row);
  }
}
$('add-keyword').onclick=()=>{clearTimeout(timer);searchKeywords=uniqueKeywords([...searchKeywords,...$('query').value.split(/\s+/)]);$('query').value='';renderKeywords();localSearch();$('query').focus();};
$('search-form').onsubmit=e=>{e.preventDefault();clearTimeout(timer);saveSearchHistory();localSearch();};
$('query').oninput=()=>{clearTimeout(timer);timer=setTimeout(()=>localSearch(),180);};
$('match-mode').onchange=()=>{
  if($('match-mode').value==='phrase'){$('query').value=uniqueKeywords([...searchKeywords,$('query').value]).join(' ');searchKeywords=[];}
  renderKeywords();saveSearchHistory();localSearch();
};
$('clear-search-history').onclick=()=>{try{localStorage.removeItem('obc-search-history');searchHistory=[];renderSearchHistory();}catch{$('status').textContent='清空历史失败，请重试。';}};
$('search-selection').addEventListener('pointerdown',e=>e.preventDefault());
$('search-selection').onclick=()=>{
  const selected=window.getSelection().toString().trim();if(!selected||!selectionParts.length)return;
  remember();
  selectionSource={id:current.id,anchor:readingAnchors[current.id]?{...readingAnchors[current.id]}:null,position:positions[current.id]||0};
 clearReadingSelection();++routeId;current=null;
  history.pushState(null,'',location.pathname+location.search);$('reader').hidden=true;$('library').hidden=false;
  searchKeywords=[selected];$('query').value='';$('match-mode').value='any';
  switchView('search',false);renderKeywords();saveSearchHistory();localSearch();window.scrollTo(0,0);
};
renderKeywords();renderSearchHistory();

function renderSelectionReturn(){
  if(!window.selectionReturnReady)return;
  const visible=Boolean(selectionSource && viewMode==='search' && !$('library').hidden);
  $('selection-return').hidden=!visible;
  document.body.classList.toggle('has-selection-return',visible);
}
function clearSelectionSource(){selectionSource=null;renderSelectionReturn();}
function returnToSelectedSource(){
  if(!selectionSource || viewMode!=='search' || $('library').hidden)return false;
  const source=selectionSource;clearSelectionSource();
  if(source.anchor)readingAnchors[source.id]={...source.anchor};
  positions[source.id]=source.position;
  activeTerms=[];navigate('#entry/'+source.id);return true;
}
window.selectionReturnReady=true;
renderSelectionReturn();
$('selection-return').onclick=returnToSelectedSource;
