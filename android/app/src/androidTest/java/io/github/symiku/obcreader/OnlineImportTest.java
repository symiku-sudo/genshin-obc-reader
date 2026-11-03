package io.github.symiku.obcreader;

import android.content.Context;
import android.content.Intent;
import android.net.ConnectivityManager;
import androidx.test.core.app.ApplicationProvider;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import org.json.JSONObject;
import com.chaquo.python.Python;
import org.junit.Test;
import org.junit.runner.RunWith;
import static org.junit.Assert.*;

@RunWith(AndroidJUnit4.class)
public class OnlineImportTest extends DeviceTestBase {
    private void launchOnline() throws Exception {
        Context context = ApplicationProvider.getApplicationContext();
        device.executeShellCommand("cmd connectivity airplane-mode disable");
        device.executeShellCommand("svc wifi enable");
        ConnectivityManager connectivity = (ConnectivityManager) context.getSystemService(Context.CONNECTIVITY_SERVICE);
        long deadline = System.currentTimeMillis() + 60000;
        while (connectivity.getActiveNetwork() == null && System.currentTimeMillis() < deadline) Thread.sleep(500);
        assertNotNull("Online test requires emulator network", connectivity.getActiveNetwork());
        android.util.Log.i("OBCStartup", "Online test network: " + connectivity.getNetworkCapabilities(connectivity.getActiveNetwork()));
        activity.launchActivity(new Intent(context, MainActivity.class));
        await("document.querySelectorAll('#results .card').length > 0");
    }

    @Test public void onlineTitleSearch() throws Exception {
        launchOnline();
        String title = api("GET", "/api/entry/763", "").getString("title");
        assertTrue(api("GET", "/api/remote?q=" + java.net.URLEncoder.encode(title, "UTF-8"), "").getJSONArray("items").length() > 0);
    }

    @Test public void onlineRefreshPreservesReadingStateAndWorksOffline() throws Exception {
        launchOnline();
        api("POST", "/api/read", "{\"id\":\"763\",\"is_read\":true}");
        JSONObject before = api("GET", "/api/entry/763", "");
        JSONObject response = null;
        for (int attempt=0; attempt<3; attempt++) {
            response = new JSONObject(Python.getInstance().getModule("android_runtime").callAttr("request", "POST", "/api/import", "{\"id\":\"763\",\"refresh\":true}").toString());
            if (response.getInt("status") != 502) break;
            JSONObject cached = api("GET", "/api/entry/763", "");
            assertEquals("Failed refresh must preserve text", before.getJSONArray("sections").toString(), cached.getJSONArray("sections").toString());
            assertTrue("Failed refresh must preserve read state", cached.getBoolean("is_read"));
            android.util.Log.i("TestRunner", "Upstream refresh temporarily unavailable, attempt " + (attempt+1));
            if (attempt<2) Thread.sleep(3000);
        }
        assertNotNull(response);
        assertEquals(response.toString(), 200, response.getInt("status"));
        JSONObject updated = response.getJSONObject("data");
        assertEquals("763", updated.getString("id"));
        assertTrue(updated.getJSONArray("sections").length() > 0);
        assertTrue(updated.getBoolean("is_read"));
        // Verify the newly downloaded text immediately remains usable without network.
        ensureOffline();
        assertEquals(updated.getJSONArray("sections").toString(), api("GET", "/api/entry/763", "").getJSONArray("sections").toString());
        asyncJs("navigate('#entry/763');");
        await("current && current.id === '763' && document.getElementById('article').textContent.length > 0");
    }
}
