'use strict';
let pendingBackup = null;
function validateBackup(data) {
  const id = v => typeof v === 'string' && /^\d{1,12}$/.test(v);
  const ids = v => Array.isArray(v) && v.length <= 20000 && v.every(id);
  if (!data || data.format !== 'obc-reading-backup' || data.version !== 1 ||
      !ids(data.read_entries) || !ids(data.bookmarks) || !data.positions ||
      typeof data.positions !== 'object' || Array.isArray(data.positions) ||
      Object.keys(data.positions).length > 20000 ||
      !Object.entries(data.positions).every(([k,v]) => id(k) && Number.isFinite(v) && v >= 0 && v <= 1e9) ||
      ![16,18,20,22,24].includes(data.font)) throw new Error('文件格式或记录内容不正确。');
  return data;
}
$('export-reading').onclick = async () => {
  $('export-reading').disabled = true;
  try {
    remember();
    const saved = await api('/api/reading-backup');
    const data = validateBackup({format:'obc-reading-backup',version:1,exported_at:new Date().toISOString(),
      read_entries:saved.read_entries,bookmarks,positions,font:fontSize});
    const filename='观测枢阅读记录-'+new Date().toISOString().slice(0,10)+'.json';
    if (window.saveReadingFile) {
      await window.saveReadingFile(filename, JSON.stringify(data,null,2));
    } else {
    const url = URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));
    const link = document.createElement('a');link.href=url;link.download='观测枢阅读记录-'+new Date().toISOString().slice(0,10)+'.json';
    document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
    }
    $('backup-status').textContent='已生成备份，请保留下载的 JSON 文件。';
  } catch(e) { $('backup-status').textContent='导出失败：'+e.message; }
  finally { $('export-reading').disabled=false; }
};
let fileVersion = 0;
$('backup-file').onchange = async () => {
  const ticket = ++fileVersion;
  pendingBackup=null;$('restore-reading').hidden=true;
  const file=$('backup-file').files[0];if(!file)return;
  try {
    if(file.size>2_000_000)throw new Error('文件超过 2 MB。');
    const data=validateBackup(JSON.parse(await file.text()));
    if(ticket!==fileVersion)return;
    pendingBackup=data;
    $('backup-status').textContent=`已读 ${new Set(data.read_entries).size} 条 · 收藏 ${new Set(data.bookmarks).size} 条 · 阅读位置 ${Object.keys(data.positions).length} 条。`;
    $('restore-reading').hidden=false;
  } catch(e) {if(ticket===fileVersion)$('backup-status').textContent='无法读取备份：'+e.message;}
};
$('restore-reading').onclick=async()=>{
  if(!pendingBackup)return;
  const data=pendingBackup;
  $('restore-reading').disabled=true;$('backup-file').disabled=true;
  try {
    await api('/api/reading-restore',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({read_entries:data.read_entries})});
    const mergedBookmarks=[...new Set([...bookmarks,...data.bookmarks])];
    const mergedPositions={...data.positions,...positions};
    const restoredFont=store.get('font',null)===null ? data.font : fontSize;
    // Use direct writes so a storage failure is reported rather than silently ignored.
    localStorage.setItem('obc-bookmarks',JSON.stringify(mergedBookmarks));
    localStorage.setItem('obc-positions',JSON.stringify(mergedPositions));
    localStorage.setItem('obc-font',JSON.stringify(restoredFont));
    bookmarks=mergedBookmarks;positions=mergedPositions;fontSize=restoredFont;entryCache.clear();
    if(current){current.is_read=(await api('/api/entry/'+current.id)).is_read;setReadButton();setBookmark();$('article').className='size-'+fontSize;}
    else if(!remoteMode)await localSearch();
    pendingBackup=null;$('restore-reading').hidden=true;$('backup-file').value='';
    $('backup-status').textContent='阅读记录已合并恢复。';
  } catch(e) { $('backup-status').textContent='恢复未全部完成，部分记录可能已合并，可重试：'+e.message; }
  finally {$('restore-reading').disabled=false;$('backup-file').disabled=false;}
};
