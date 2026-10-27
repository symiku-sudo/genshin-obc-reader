'use strict';
(() => {
  let sequence = 0;
  const pending = new Map();
  const call = (kind, ...args) => new Promise((resolve, reject) => {
    const id = String(++sequence);
    pending.set(id, {resolve, reject});
    try { ReaderNative[kind](id, ...args); }
    catch (e) { pending.delete(id); reject(e); }
  });
  window.readerNativeResult = (id, response) => {
    const item = pending.get(id);
    if (!item) return;
    pending.delete(id);
    if (response.error) item.reject(new Error(response.error));
    else item.resolve(response);
  };
  const originalFetch = window.fetch.bind(window);
  window.fetch = async (url, options = {}) => {
    if (typeof url !== 'string' || !url.startsWith('/api/')) {
      return originalFetch(typeof url === 'string' && url.startsWith('/') ? '/web' + url : url, options);
    }
    const result = await call('request', options.method || 'GET', url, options.body || '');
    return new Response(JSON.stringify(result.data), {status: result.status, headers: {'Content-Type': 'application/json'}});
  };
  window.saveReadingFile = (name, data) => call('saveDocument', name, data);
  window.readerBack = () => {
    const modal = document.querySelector('dialog[open]');
    if (modal) { modal.close(); return true; }
    if (location.hash) { document.getElementById('back').click(); return true; }
    return false;
  };
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden' && typeof remember === 'function') remember();
  });
})();
