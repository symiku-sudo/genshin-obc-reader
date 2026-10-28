package io.github.symiku.obcreader;

import android.content.Context;
import android.content.Intent;
import android.net.ConnectivityManager;
import androidx.test.core.app.ApplicationProvider;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.uiautomator.By;
import androidx.test.uiautomator.UiObject2;
import androidx.test.uiautomator.Until;
import com.chaquo.python.Python;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import static org.junit.Assert.*;

@RunWith(AndroidJUnit4.class)
public class OfflineTest extends DeviceTestBase {
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
        openDownloads();
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
        touchBackupChooser();
        openDownloads();
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

        JSONObject expected = new JSONObject();
        for (String key : new String[]{"font", "positions", "bookmarks"}) {
            expected.put(key, js("localStorage.getItem('obc-"+key+"')"));
        }
        expected.put("reading", api("GET", "/api/reading-backup", "").getJSONArray("read_entries").toString());
        String job = api("GET", "/api/library", "").getJSONArray("jobs").getJSONObject(0).getString("id");
        expected.put("interrupted_job", job);
        // Simulate a killed import process in this test-only database, without network.
        Python.getInstance().getModule("builtins").callAttr("exec", "import core\nwith core.connect() as db:\n db.execute(\"UPDATE jobs SET state='running' WHERE id=?\", ("+JSONObject.quote(job)+",))");
        try (FileOutputStream out = new FileOutputStream(new File(context.getFilesDir(), "test-expected.json"))) {
            out.write(expected.toString().getBytes(StandardCharsets.UTF_8));
        }

    }
}
