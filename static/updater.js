'use strict';
(() => {
  if(typeof window.readerAppUpdate!=='function')return;
  $('app-update').hidden=false;
  let pollTimer, lastState, actionPending=false, notificationDismissed=false;
  const bytes=n=>(Number(n)/1048576).toFixed(1)+' MiB';
  function render(state){
    lastState=state;
    const release=state.release||{},available=Boolean(release.version);
    $('app-version').textContent='当前版本 '+state.installed;
    $('app-update-version').textContent=available?'新版本 '+release.version+' · '+bytes(release.size):'';
    $('app-update-notes').textContent=release.notes||'';
    $('app-update-details').hidden=!available;
    $('app-update-page').href=release.page||'https://github.com/symiku-sudo/genshin-obc-reader/releases/latest';
    const labels={preparing:'正在确认安装包并连接下载…',checking:'正在检查最新版本…',downloading:'正在下载安装包…',verifying:'正在校验安装包…',paused:'下载已暂停，进度已保留。',ready:'安装包已校验，可以安装更新。',idle:available?'有新版本可供下载。':'尚未发现新版本。'};
    $('app-update-status').textContent=state.message||labels[state.phase]||'';
    const progress=$('app-update-progress');progress.hidden=!available||(!state.received&&state.phase!=='downloading');
    progress.max=release.size||1;progress.value=state.received||0;
    $('app-update-count').textContent=progress.hidden?'':bytes(state.received)+' / '+bytes(release.size)+' · '+Math.min(100,Math.floor(state.received*100/release.size))+'%';
    $('app-update-check').disabled=Boolean(state.busy)||actionPending;
    $('app-update-download').hidden=!available||state.phase==='ready';
    $('app-update-download').disabled=Boolean(state.busy)||actionPending;
    $('app-update-download').textContent=state.received?'继续下载':state.phase==='paused'?'重试下载':'下载更新';
    $('app-update-pause').hidden=!['downloading','preparing'].includes(state.phase)||!state.busy||!available;
    $('app-update-install').hidden=state.phase!=='ready';
    $('app-update-install').disabled=Boolean(state.busy)||actionPending;
    $('app-update-notice').hidden=!available||notificationDismissed;
    $('app-update-notice-text').textContent='发现新版本 '+(release.version||'');
    clearTimeout(pollTimer);
    if(state.busy&&document.visibilityState!=='hidden')pollTimer=setTimeout(()=>request('status'),700);
  }
  async function request(action){
    if(action!=='status'){actionPending=true;if(lastState)render(lastState);}
    try{
      const state=await window.readerAppUpdate(action);
      actionPending=false;
      if(action==='install'){
        await request('status');$('app-update-status').textContent='请在系统安装器中确认更新。';
      }else render(state);
    }catch(e){actionPending=false;if(lastState)render(lastState);$('app-update-status').textContent=e.message;}
  }
  for(const [id,action] of [['check','check'],['download','download'],['pause','pause'],['install','install']])$('app-update-'+id).onclick=()=>request(action);
  $('app-update-notice-open').onclick=()=>{$('open-management').click();$('app-update').open=true;$('app-update').scrollIntoView({block:'start'});};
  $('app-update-notice-dismiss').onclick=()=>{notificationDismissed=true;$('app-update-notice').hidden=true;};
  $('app-update').addEventListener('toggle',()=>{if($('app-update').open)request('status');});
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')request('status');else clearTimeout(pollTimer);});
  request('auto');
})();
