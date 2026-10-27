const fs = require('fs');
const vm = require('vm');
const assert = require('node:assert/strict');
let sent, fetched;
const context = {
  Response, Map, Promise, Error,
  ReaderNative: {
    request(...args) { sent = args; },
    saveDocument(...args) { sent = args; }
  },
  document: {addEventListener() {}},
  window: {fetch: (...args) => {fetched=args; return Promise.resolve('static');}}
};
vm.runInNewContext(fs.readFileSync('android/runtime.js','utf8'), context);
(async () => {
  assert.equal(await context.window.fetch('/catalog-channels.json'), 'static');
  assert.equal(fetched[0], '/web/catalog-channels.json');
  const response = context.window.fetch('/api/search?read=unread');
  assert.deepEqual(sent, ['1','GET','/api/search?read=unread','']);
  context.window.readerNativeResult('1',{status:200,data:{total:3616}});
  assert.deepEqual(await (await response).json(), {total:3616});
  const error = context.window.fetch('/api/entry/999');
  context.window.readerNativeResult('2',{status:404,data:{error:'词条尚未缓存'}});
  assert.equal((await error).status,404);
  const save = context.window.saveReadingFile('reading.json','{}');
  context.window.readerNativeResult('3',{saved:true});
  assert.equal((await save).saved,true);
  const cancel = context.window.saveReadingFile('reading.json','{}');
  context.window.readerNativeResult('4',{error:'已取消保存'});
  await assert.rejects(cancel,/已取消保存/);
  console.log('Android bridge checks passed: API, static assets, HTTP errors, document save/cancel.');
})().catch(e=>{console.error(e);process.exitCode=1;});
