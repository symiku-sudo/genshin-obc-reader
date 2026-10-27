'use strict';
let librarySignature = '', collectionReady = false, jobId = '', jobPage = 1, jobPages = 1;
const jobNames = {queued:'排队中',scanning:'核对目录',running:'导入中',pausing:'正在暂停',paused:'已暂停',completed:'本轮结束',failed:'任务中断'};
const countNames = {success:'已更新',unchanged:'未变化',no_text:'无所需文本',review:'待适配',failed:'获取失败'};
async function refreshLibrary() {
  const data = await api('/api/library');
  if (!collectionReady) {
    $('collection-options').innerHTML = data.categories.map(c => `<label><input type="checkbox" value="${esc(c.id)}"> ${esc(c.name)} <span id="collection-${esc(c.id)}"></span></label>`).join('');
    collectionReady = true;
    loadCoverage(data.categories);
  }
  data.categories.forEach(c => {
    $('collection-' + c.id).textContent = c.total == null ? '尚未获取目录' : `目录 ${c.total} · 已缓存 ${c.cached}` + (c.unlisted ? ` · 原站已移出目录 ${c.unlisted}` : '');
  });
  $('library-storage').textContent = `本地数据库 ${(data.database_bytes / 1048576).toFixed(1)} MB · 迁移备份 ${(data.backup_bytes / 1048576).toFixed(1)} MB`;
  const active = data.jobs.filter(j => ['queued','scanning','running','pausing'].includes(j.state));
  $('library-mini').textContent = active.length ? `· ${active.length} 个任务进行中` : '· 分类导入与更新';
  const signature = JSON.stringify(data.jobs);
  if (signature !== librarySignature) {
    if (librarySignature) entryCache.clear();
    librarySignature = signature;
    function renderJob(j) {
      const counts = Object.entries(countNames).map(([k,v]) => `${v} ${j.counts[k]}`).join(' · ');
      const buttons = ['queued','scanning','running'].includes(j.state) ? `<button data-action="pause" data-job="${j.id}">暂停</button>` : ['paused','failed'].includes(j.state) ? `<button data-action="resume" data-job="${j.id}">继续</button>` : '';
      const recheck = j.counts.review && ['completed','paused','failed'].includes(j.state) ? `<button data-action="recheck" data-job="${j.id}">重查待适配</button>` : '';
      const retry = j.counts.failed && ['completed','paused','failed'].includes(j.state) ? `<button data-action="retry" data-job="${j.id}">重试失败项</button>` : '';
      return `<div class="job"><div class="job-heading"><strong>${esc(j.name)} · 导入任务</strong><span>${jobNames[j.state] || esc(j.state)} · ${j.done} / ${j.total || '待确定'}</span></div><progress max="${j.total || 1}" value="${j.done}"></progress><p>创建于 ${esc(new Date(j.created_at).toLocaleString('zh-CN'))}</p><p>${counts}</p>${j.error ? `<p class="job-error">${esc(j.error)}</p>` : ''}<div class="job-actions">${buttons}${retry}${recheck}<button data-view="${j.id}">查看结果</button></div></div>`;
    }
    const pending = data.jobs.filter(j => j.state !== 'completed');
    const history = data.jobs.filter(j => j.state === 'completed');
    $('current-jobs').innerHTML = pending.map(renderJob).join('') || '<p class="manager-hint">没有进行中或待处理的任务。</p>';
    $('past-jobs').innerHTML = history.map(renderJob).join('') || '<p class="manager-hint">暂无已结束的任务。</p>';
    $('history-count').textContent = `（${history.length} 次）`;
    updateStats().catch(() => {});
  }
}
async function loadCoverage(supported) {
  try {
    const data = await api('/catalog-channels.json');
    const names = new Set(supported.map(c => c.name));
    const groups = new Map();
    for (const c of data.categories) {
      if (names.has(c.name)) continue;
      if (!groups.has(c.group)) groups.set(c.group, []);
      groups.get(c.group).push(c);
    }
    $('unsupported-categories').innerHTML = [...groups].map(([group, items]) => `<section><h4>${esc(group)}</h4><ul>${items.map(c => `<li>${esc(c.name)} <span>未接入批量导入</span></li>`).join('')}</ul></section>`).join('');
  } catch(e) { $('coverage-status').textContent = '目录展示暂时不可用，请刷新重试。'; }
}
$('start-import').onclick = async () => {
  const categories = [...$('collection-options').querySelectorAll('input:checked')].map(x => x.value);
  if (!categories.length) { $('import-status').textContent = '请至少选择一个分类。'; return; }
  $('start-import').disabled = true;
  try {
    await api('/api/jobs/start', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({categories})});
    $('import-status').textContent = '任务已创建；已有任务会继续保留。如已暂停，请点“继续”。';
    await refreshLibrary();
  } catch(e) { $('import-status').textContent = e.message; }
  finally { $('start-import').disabled = false; }
};
$('import-jobs').addEventListener('click', async e => {
  const b = e.target.closest('button'); if (!b) return;
  if (b.dataset.view) { jobId=b.dataset.view;jobPage=1;$('job-results').hidden=false;await loadJobDetails();return; }
  if (b.dataset.action) {
    b.disabled = true;
    try {
      await api('/api/jobs/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:b.dataset.job,action:b.dataset.action})});
      $('import-status').textContent = '';await refreshLibrary();
    } catch(err) { $('import-status').textContent=err.message; b.disabled=false; }
  }
});
async function loadJobDetails() {
  if (!jobId) return;
  const requestedId=jobId, requestedPage=jobPage, requestedState=$('job-filter').value;
  try {
    const data=await api('/api/job?id='+encodeURIComponent(jobId)+'&state='+encodeURIComponent(requestedState)+'&page='+jobPage);
    if(jobId!==requestedId || jobPage!==requestedPage || $('job-filter').value!==requestedState)return;
    $('job-results-title').textContent=data.name+' · 导入结果';
    $('job-detail-status').textContent='待适配可能已保存部分文本；“无所需文本”指按当前规则未找到故事、描述等正文。';
    $('job-items').innerHTML=data.items.map(x => {
      const available=['success','unchanged'].includes(x.state) || x.details.retained_old || (x.state==='review' && x.details.sections>0);
      return `<div class="job-item"><span>${esc(x.title)}</span><span class="job-item-state">${esc(x.label)}${x.details.retained_old ? ' · 已保留旧正文' : ''}</span>${available ? `<a href="#entry/${x.entry_id}">阅读</a>` : `<a href="https://baike.mihoyo.com/ys/obc/content/${x.entry_id}/detail" target="_blank" rel="noopener noreferrer">原站 ↗</a>`}${x.error ? `<p class="job-error">${esc(x.error)}</p>` : ''}</div>`;
    }).join('') || '<p class="manager-hint">此状态下没有词条。</p>';
    jobPages=Math.max(1,Math.ceil(data.item_total/40));
    $('job-page').textContent=`${jobPage} / ${jobPages}`;
    $('job-prev').disabled=jobPage<=1;$('job-next').disabled=jobPage>=jobPages;
  } catch(e) { $('job-detail-status').textContent=e.message; }
}
$('job-filter').onchange=()=>{jobPage=1;loadJobDetails();};
$('job-prev').onclick=()=>{if(jobPage>1){jobPage--;loadJobDetails();}};
$('job-next').onclick=()=>{if(jobPage<jobPages){jobPage++;loadJobDetails();}};
$('close-job-results').onclick=()=>{$('job-results').hidden=true;jobId='';};
$('library-manager').addEventListener('toggle',()=>{if($('management').open && $('library-manager').open)refreshLibrary().catch(e=>{$('import-status').textContent=e.message;});});
async function libraryPoll() {
  if(!document.hidden && $('management').open) {
    try { await refreshLibrary(); if(jobId && $('library-manager').open)await loadJobDetails(); }
    catch(e) { $('library-mini').textContent='· 暂时无法连接服务'; }
  }
  setTimeout(libraryPoll,3000);
}
libraryPoll();
