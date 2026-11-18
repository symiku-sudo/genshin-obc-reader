package io.github.symiku.obcreader;

import android.content.Context;
import android.content.Intent;
import androidx.test.core.app.ApplicationProvider;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import org.json.JSONObject;
import org.json.JSONArray;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.io.*;
import java.net.*;
import java.nio.file.Files;
import java.util.*;
import static org.junit.Assert.*;

@RunWith(AndroidJUnit4.class)
public class Version131Test extends DeviceTestBase {
    Context context=ApplicationProvider.getApplicationContext();
    private File fixture(String name) throws Exception {
        File file=new File(context.getCacheDir(),name);
        try(InputStream in=InstrumentationRegistry.getInstrumentation().getContext().getAssets().open(name);OutputStream out=new FileOutputStream(file)){
            byte[] b=new byte[8192];int n;while((n=in.read(b))!=-1)out.write(b,0,n);
        }return file;
    }
    private JSONObject release(File file) throws Exception {
        return new JSONObject().put("tag_name","v1.3.3").put("draft",false).put("prerelease",false).put("body","测试更新说明")
            .put("assets",new JSONArray().put(new JSONObject().put("id",123).put("name","obc-reader-1.3.3.apk").put("size",file.length()).put("digest","sha256:"+AppUpdater.sha256(file)).put("state","uploaded").put("browser_download_url",AppUpdater.REPO+"/releases/download/v1.3.3/obc-reader-1.3.3.apk")));
    }
    private AppUpdater updater(String name,FakeServer server){
        return new AppUpdater(context,"test-update-"+name,new File(context.getCacheDir(),"updates-"+name),server);
    }
    private void finished(AppUpdater updater) throws Exception {
        long end=System.currentTimeMillis()+15000;
        while(updater.status().getBoolean("busy")&&System.currentTimeMillis()<end)Thread.sleep(20);
        assertFalse(updater.status().toString(),updater.status().getBoolean("busy"));
    }
    static class FakeServer implements AppUpdater.Connections {
        JSONObject release;byte[] bytes;boolean interrupt,ignoreRange,badRange;Runnable onRead;int metadataCalls;
        List<Long> offsets=new ArrayList<>();
        FakeServer(JSONObject release,byte[] bytes){this.release=release;this.bytes=bytes;}
        public HttpURLConnection open(URL url,long offset) throws Exception {
            boolean metadata=url.toString().equals(AppUpdater.API);
            if(metadata)metadataCalls++;else offsets.add(offset);
            byte[] body=metadata?release.toString().getBytes("UTF-8"):bytes;
            boolean ranged=!metadata&&offset>0&&!ignoreRange;
            int start=ranged?(int)offset:0;
            return new HttpURLConnection(url){
                public int getResponseCode(){return ranged?206:200;}
                public long getContentLengthLong(){return body.length-start;}
                public String getHeaderField(String key){return badRange?"bytes 0-1/2":"bytes "+start+"-"+(body.length-1)+"/"+body.length;}
                public InputStream getInputStream(){
                    return new InputStream(){int position=start,reads=0;
                        public int read() throws IOException{byte[] b=new byte[1];return read(b,0,1)<0?-1:b[0]&255;}
                        public int read(byte[] b,int off,int len)throws IOException{
                            if(!metadata&&interrupt&&reads>0)throw new IOException("simulated network loss");
                            if(position==body.length)return -1;
                            int n=Math.min(Math.min(len,1024),body.length-position);System.arraycopy(body,position,b,off,n);position+=n;reads++;
                            if(!metadata&&onRead!=null){Runnable callback=onRead;onRead=null;callback.run();}
                            return n;
                        }
                    };
                }
                public void disconnect(){} public boolean usingProxy(){return false;}public void connect(){}
            };
        }
    }
    @Test public void versionAndReleaseValidation() throws Exception {
        assertTrue(AppUpdater.newer("1.10.0","1.9.9"));assertFalse(AppUpdater.newer("1.3.1","1.3.1"));assertFalse(AppUpdater.newer("1.3.3-beta","1.3.1"));assertFalse(AppUpdater.newer("9999999999.0.0","1.3.1"));
        JSONObject data=release(fixture("update-valid.apk"));assertEquals("1.3.3",AppUpdater.parseRelease(data,"1.3.1").getString("version"));
        assertEquals(0,AppUpdater.parseRelease(data,"1.3.3").length());
        data.getJSONArray("assets").getJSONObject(0).put("browser_download_url","https://evil.example/update.apk");
        try{AppUpdater.parseRelease(data,"1.3.1");fail("foreign URL accepted");}catch(IOException expected){}
        try{AppUpdater.open(new URL("http://github.com/a"),0);fail("insecure URL accepted");}catch(IOException expected){}
        try{AppUpdater.validateRange("bytes 0-9/10",5,10);fail("wrong range accepted");}catch(IOException expected){}
    }
    @Test public void resumeAcrossRecreationAndServerChanges() throws Exception {
        File file=fixture("update-valid.apk");byte[] bytes=Files.readAllBytes(file.toPath());
        String key=UUID.randomUUID().toString();FakeServer server=new FakeServer(release(file),bytes);server.interrupt=true;
        AppUpdater first=updater(key,server);first.download();finished(first);
        assertEquals("paused",first.status().getString("phase"));assertEquals(1024,first.status().getLong("received"));
        server.interrupt=false;
        AppUpdater resumed=updater(key,server);assertEquals(1024,resumed.status().getLong("received"));resumed.download();finished(resumed);
        assertEquals(resumed.status().toString(),"ready",resumed.status().getString("phase"));assertEquals(Long.valueOf(1024),server.offsets.get(1));
        // A server ignoring Range must replace the partial file, never append.
        key=UUID.randomUUID().toString();server=new FakeServer(release(file),bytes);server.interrupt=true;
        first=updater(key,server);first.download();finished(first);server.interrupt=false;server.ignoreRange=true;first.download();finished(first);
        assertEquals(first.status().toString(),"ready",first.status().getString("phase"));
        // Changed release asset invalidates the previous prefix before the next request.
        key=UUID.randomUUID().toString();server=new FakeServer(release(file),bytes);server.interrupt=true;
        first=updater(key,server);first.download();finished(first);server.interrupt=false;server.release.getJSONArray("assets").getJSONObject(0).put("id",124);first.download();finished(first);
        assertEquals(Long.valueOf(0),server.offsets.get(1));assertEquals("ready",first.status().getString("phase"));
    }
    @Test public void pauseChecksumSignatureAndDailyCheck() throws Exception {
        File file=fixture("update-valid.apk");FakeServer server=new FakeServer(release(file),Files.readAllBytes(file.toPath()));
        AppUpdater updater=updater(UUID.randomUUID().toString(),server);
        server.onRead=updater::pause;updater.download();finished(updater);assertEquals("paused",updater.status().getString("phase"));
        updater.download();finished(updater);assertEquals("ready",updater.status().getString("phase"));
        JSONObject valid=AppUpdater.parseRelease(release(file),"1.3.1");updater.verify(file,valid);
        File invalid=fixture("update-wrong-signer.apk");JSONObject wrong=AppUpdater.parseRelease(release(invalid),"1.3.1");
        try{updater.verify(invalid,wrong);fail("wrong signing identity accepted");}catch(IOException expected){assertTrue(expected.getMessage().contains("签名"));}
        valid.put("sha256",String.join("",Collections.nCopies(64,"0")));
        try{updater.verify(file,valid);fail("wrong checksum accepted");}catch(IOException expected){assertTrue(expected.getMessage().contains("校验"));}
        server=new FakeServer(release(file),Files.readAllBytes(file.toPath()));updater=updater(UUID.randomUUID().toString(),server);
        updater.check(false);finished(updater);updater.check(false);finished(updater);assertEquals(1,server.metadataCalls);
        updater.check(true);finished(updater);assertEquals(2,server.metadataCalls);
    }
    @Test public void fullPageHighlightsAndNativeUpdateBridge() throws Exception {
        ensureOffline();activity.launchActivity(new Intent(context,MainActivity.class));await("document.querySelectorAll('#results .card').length>0");
        js("window.oldTestHighlights=highlights;highlights=Array.from({length:125},(_,i)=>({id:'qa'+i,entry:'1600',title:'测试来源',created:i,parts:[{section:'section-0',paragraph:0,start:0,end:2,quote:'测试划线'+i}],note:i===9?'单关键词':''}));document.getElementById('open-highlights').click();true");
        await("!document.getElementById('highlights-page').hidden && document.querySelectorAll('.highlight-card').length===50");
        check("document.getElementById('library').hidden && document.getElementById('reader').hidden");
        js("document.getElementById('highlights-more').click();true");check("document.querySelectorAll('.highlight-card').length===100");
        await("document.getElementById('highlight-category').options.length>1");
        device.takeScreenshot(new File(context.getExternalFilesDir(null),"highlights-131.png"));
        check("getComputedStyle(document.querySelector('.mast')).display==='none'");
        check("!document.querySelector('.highlight-more').open");
        js("document.querySelector('.highlight-more summary').click();true");
        check("document.querySelector('.highlight-more').open");
        device.takeScreenshot(new File(context.getExternalFilesDir(null),"highlights-menu-132.png"));
        js("document.querySelector('.highlight-more summary').click();true");
        js("document.getElementById('highlight-query').value='单关键词';document.getElementById('highlight-query').dispatchEvent(new Event('input'));true");check("document.querySelectorAll('.highlight-card').length===1");
        asyncJs("const state=await readerAppUpdate('status');if(state.installed!=='1.3.2')throw Error('version');");
        check("!document.getElementById('app-update').hidden");
        js("highlights=window.oldTestHighlights;document.getElementById('highlight-query').value='';document.getElementById('close-highlights').click();true");
        js("navigate('');window.scrollTo(0,0);true");
        await("!document.getElementById('library').hidden");
        device.takeScreenshot(new File(context.getExternalFilesDir(null),"library-132.png"));
        js("navigate('#entry/1600');true");
        await("current && current.id==='1600'");
        js("fontSize=18;document.getElementById('article').className='size-18';window.scrollTo(0,0);true");
        device.takeScreenshot(new File(context.getExternalFilesDir(null),"reader-132.png"));
        js("document.querySelector('#reading-appearance summary').click();true");
        check("document.getElementById('reading-appearance').open");
        js("document.getElementById('larger').click();true");
        check("document.getElementById('article').className==='size-20'");
        js("document.querySelector('#reading-appearance summary').click();true");
    }
}
