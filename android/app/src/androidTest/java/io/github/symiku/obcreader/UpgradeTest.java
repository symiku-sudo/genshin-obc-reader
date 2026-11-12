package io.github.symiku.obcreader;

import android.content.Context;
import android.content.Intent;
import androidx.test.core.app.ApplicationProvider;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.io.File;
import java.nio.file.Files;
import java.nio.charset.StandardCharsets;
import static org.junit.Assert.*;

@RunWith(AndroidJUnit4.class)
public class UpgradeTest extends DeviceTestBase {
    @Test public void realVersionUpgradePreservesRecordsAndAddsTasks() throws Exception {
        Context context = ApplicationProvider.getApplicationContext();
        boolean seed = "seed".equals(InstrumentationRegistry.getArguments().getString("upgradePhase"));
        ensureOffline();
        long started = System.currentTimeMillis();
        activity.launchActivity(new Intent(context, MainActivity.class));
        await("document.querySelectorAll('#results .card').length > 0");
        File snapshot = new File(context.getFilesDir(), "upgrade-expected.json");
        String[] keys = {"bookmarks", "positions", "anchors", "highlights", "font", "search-history", "recent-readings", "last-reading"};
        if (seed) {
            assertEquals("1.2.1", context.getPackageManager().getPackageInfo(context.getPackageName(), 0).versionName);
            api("POST", "/api/read", "{\"id\":\"1600\",\"is_read\":true}");
            js("navigate('#entry/1600');true");
            await("current && current.id==='1600' && prose().length>0");
            js("if(!bookmarks.includes('1600'))document.getElementById('bookmark').click();const p=prose().find(p=>p.textContent.length>20);getSelection().removeAllRanges();getSelection().addRange(characterRange(p,0,2));document.dispatchEvent(new Event('selectionchange'));document.getElementById('annotate-selection').click();true");
            await("document.getElementById('note-editor').open");
            js("document.getElementById('note-text').value='升级保留笔记';document.getElementById('save-note').click();window.scrollTo(0,600);remember();true");
            await("highlights.some(h=>h.note==='升级保留笔记') && positions['1600']>0");
            js("navigate('#library');true");
            await("!document.getElementById('library').hidden");
            JSONObject expected = new JSONObject();
            for (String key : keys) expected.put(key, js("localStorage.getItem('obc-"+key+"')"));
            expected.put("reading", api("GET", "/api/reading-backup", "").getJSONArray("read_entries").toString());
            Files.write(snapshot.toPath(), expected.toString().getBytes(StandardCharsets.UTF_8));
        } else {
            assertEquals("1.3.0", context.getPackageManager().getPackageInfo(context.getPackageName(), 0).versionName);
            JSONObject expected = new JSONObject(new String(Files.readAllBytes(snapshot.toPath()), StandardCharsets.UTF_8));
            for (String key : keys) assertEquals("Preserved " + key, expected.getString(key), js("localStorage.getItem('obc-"+key+"')"));
            assertEquals(expected.getString("reading"), api("GET", "/api/reading-backup", "").getJSONArray("read_entries").toString());
            assertEquals(corpusManifest().getInt("entries"), api("GET", "/api/stats", "").getInt("entries"));
            check("highlights.some(h=>h.note==='升级保留笔记')");
            for (String category : new String[]{"魔神任务", "世界任务", "传说任务", "邀约任务", "限时任务"}) {
                assertTrue(api("GET", "/api/search?category="+java.net.URLEncoder.encode(category,"UTF-8"), "").getInt("total") > 0);
            }
            Files.write(new File(context.getExternalFilesDir(null), "upgrade-timing.txt").toPath(), ("Startup and verification ms="+(System.currentTimeMillis()-started)).getBytes(StandardCharsets.UTF_8));
        }
    }
}
