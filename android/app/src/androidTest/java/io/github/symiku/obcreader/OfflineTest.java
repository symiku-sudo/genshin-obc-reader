package io.github.symiku.obcreader;

import android.content.Context;
import android.net.ConnectivityManager;
import java.io.File;
import androidx.test.uiautomator.By;
import androidx.test.uiautomator.UiDevice;
import androidx.test.uiautomator.UiObject2;
import androidx.test.uiautomator.Until;
import org.junit.After;
import android.content.Intent;
import androidx.test.core.app.ApplicationProvider;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.rule.ActivityTestRule;
import com.chaquo.python.Python;
import org.json.JSONObject;
import org.junit.Rule;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import static org.junit.Assert.*;

@RunWith(AndroidJUnit4.class)
public class OfflineTest {
    @Rule public ActivityTestRule<MainActivity> activity = new ActivityTestRule<>(MainActivity.class, false, false);

    private String js(String expression) throws Exception {
        CountDownLatch done = new CountDownLatch(1);
        AtomicReference<String> value = new AtomicReference<>();
        InstrumentationRegistry.getInstrumentation().runOnMainSync(() -> {
            if (activity.getActivity().web == null) { value.set("null"); done.countDown(); return; }
            activity.getActivity().web.evaluateJavascript(expression, result -> { value.set(result); done.countDown(); });
        });
        assertTrue(done.await(10, TimeUnit.SECONDS));
        return value.get();
    }
    private void await(String expression) throws Exception {
        long deadline = System.currentTimeMillis() + 180000;
        while (System.currentTimeMillis() < deadline) {
            assertNull("Native startup failure", activity.getActivity().startupError);
            if ("true".equals(js(expression))) return;
            Thread.sleep(300);
        }
        fail("WebView condition timed out: " + expression);
    }
    private JSONObject api(String method, String path, String body) throws Exception {
        JSONObject result = new JSONObject(Python.getInstance().getModule("android_runtime").callAttr("request", method, path, body).toString());
        assertEquals(result.toString(), 200, result.getInt("status"));
        return result.getJSONObject("data");
    }

    private void asyncJs(String expression) throws Exception {
        js("window.testDone=false; window.testError=null; Promise.resolve().then(async()=>{" + expression + "}).then(()=>window.testDone=true,e=>{window.testError=String(e);window.testDone=true}); true");
        await("window.testDone === true");
        assertEquals("null", js("window.testError"));
    }
    private void check(String expression) throws Exception { assertEquals(expression, "true", js(expression)); }
    private final UiDevice device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation());
    private UiObject2 systemText(String expression) {
        UiObject2 object = device.wait(Until.findObject(By.text(java.util.regex.Pattern.compile(expression))), 15000);
        assertNotNull("System document control: " + expression, object);
        return object;
    }
    @After public void captureScreen() throws Exception {
        File directory = ApplicationProvider.getApplicationContext().getExternalFilesDir(null);
        device.takeScreenshot(new File(directory, "android-screen.png"));
        device.dumpWindowHierarchy(new File(directory, "android-window.xml"));
    }

    @Test public void completeCorpusAndReadingWorkWithoutNetwork() throws Exception {
        // Assert actual Android connectivity, not merely that a shell command ran.
        Context context = ApplicationProvider.getApplicationContext();
        ConnectivityManager connectivity = (ConnectivityManager) context.getSystemService(Context.CONNECTIVITY_SERVICE);
        assertNull("Offline test requires no active Android network", connectivity.getActiveNetwork());
        activity.launchActivity(new Intent(ApplicationProvider.getApplicationContext(), MainActivity.class));
        await("document.querySelectorAll('#results .card').length > 0");
        JSONObject stats = api("GET", "/api/stats", "");
        assertEquals(3616, stats.getInt("entries"));
        assertEquals(17489, stats.getInt("sections"));
        assertEquals(7, api("GET", "/api/library", "").getJSONArray("categories").length());

        // Exercise pagination and every category through the real WebView bridge.
        asyncJs("const stats=await api('/api/stats'); for(const category of stats.categories){ const result=await api('/api/search?category='+encodeURIComponent(category)); if(!result.total || result.items.some(x=>x.category!==category)) throw Error('category filter'); } for(const type of stats.text_types){const result=await api('/api/search?type='+encodeURIComponent(type));if(!result.total)throw Error('text-type filter');} const first=await api('/api/search'); const second=await api('/api/search?page=2');if(first.items.some(a=>second.items.some(b=>a.id===b.id)))throw Error('pagination overlap');");
        js("document.getElementById('local-next').click(); true");
        await("document.getElementById('local-page').textContent.startsWith('2 /')");
        js("document.getElementById('local-prev').click(); true");
        await("document.getElementById('local-page').textContent.startsWith('1 /')");
        String id = api("GET", "/api/search", "").getJSONArray("items").getJSONObject(0).getString("id");
        api("POST", "/api/read", "{\"id\":\"" + id + "\",\"is_read\":true}");
        assertTrue(api("GET", "/api/entry/" + id, "").getBoolean("is_read"));
        assertEquals(1, api("GET", "/api/search?read=read", "").getInt("total"));
        js("document.querySelector('#results a').click(); true");
        await("document.querySelector('#article').textContent.length > 0");
        js("document.getElementById('mark-read').click(); true");
        await("current && !current.is_read && !document.getElementById('mark-read').disabled");
        js("document.getElementById('mark-read').click(); true");
        await("current && current.is_read && !document.getElementById('mark-read').disabled");
        js("document.getElementById('bookmark').click(); true");
        await("JSON.parse(localStorage.getItem('obc-bookmarks')).length === 1");
        js("document.getElementById('open-management').click(); true");
        await("document.getElementById('management').open");
        assertEquals("true", js("readerBack()"));
        assertEquals("false", js("document.getElementById('management').open"));
        assertEquals("true", js("readerBack()"));
        await("!document.getElementById('library').hidden");
        // Search exact title, then follow a real snippet anchor into the full text.
        asyncJs("const entry=await api('/api/entry/1600'); switchView('search'); document.getElementById('query').value=entry.title; document.getElementById('match-mode').value='phrase'; await localSearch(); if(!lastItems.some(x=>x.id==='1600'))throw Error('title search'); document.getElementById('query').value=entry.sections[0].text.trim().slice(0,10); await localSearch(); if(!document.querySelector('#results mark'))throw Error('highlight'); window.testLink=document.querySelector('#results a').getAttribute('href'); document.querySelector('#results a').click();");
        await("!document.getElementById('reader').hidden && document.querySelector('#article mark') !== null");
        check("location.hash===window.testLink");
        js("document.getElementById('larger').click(); window.scrollTo(0,800); remember(); true");
        await("Number(JSON.parse(localStorage.getItem('obc-positions'))[current.id]) > 0");
        String font = js("localStorage.getItem('obc-font')");
        String positions = js("localStorage.getItem('obc-positions')");
        // Real native save chooser: export a validated backup to device documents.
        js("document.getElementById('open-management').click(); document.getElementById('reading-backup').open=true; document.getElementById('export-reading').click(); true");
        UiObject2 filename = device.wait(Until.findObject(By.clazz("android.widget.EditText")),15000);
        assertNotNull("Document filename field",filename);
        filename.setText("obc-offline-test.json");
        systemText("(?i)save|保存").click();
        await("!document.getElementById('export-reading').disabled");
        check("document.getElementById('backup-status').textContent.includes('已生成')");
        // Remove the saved flag and favorite, so restore must actually recover them.
        api("POST", "/api/read", "{\"id\":\"" + id + "\",\"is_read\":false}");
        js("bookmarks=[];store.set('bookmarks',bookmarks);true");
        // Open the same exported file using Android's actual file picker.
        js("document.getElementById('backup-file').click(); true");
        systemText("obc-offline-test.json").click();
        await("!document.getElementById('restore-reading').hidden");
        js("document.getElementById('restore-reading').click(); true");
        await("document.getElementById('backup-status').textContent.includes('已合并恢复')");
        assertTrue(api("GET", "/api/entry/" + id, "").getBoolean("is_read"));
        check("bookmarks.length===1");
        // Native Back, rather than a page-only simulation.
        device.pressBack();
        await("!document.getElementById('management').open");
        activity.finishActivity();
        activity.launchActivity(new Intent(context, MainActivity.class));
        await("document.querySelectorAll('#results .card').length > 0");
        assertEquals(font,js("localStorage.getItem('obc-font')"));
        assertEquals(positions,js("localStorage.getItem('obc-positions')"));
        assertTrue(api("GET", "/api/entry/" + id, "").getBoolean("is_read"));
        check("JSON.parse(localStorage.getItem('obc-bookmarks')).length===1");
        asyncJs("document.getElementById('read-filter').value='read';await localSearch(); if(localTotal!==1)throw Error('read filter'); document.getElementById('read-filter').value='unread';await localSearch();if(localTotal!==3615)throw Error('unread filter'); document.getElementById('read-filter').value='all';document.getElementById('favorites').checked=true;await localSearch();if(localTotal!==1)throw Error('favorite filter'); document.getElementById('favorites').checked=false;await localSearch();");

    }
}
