package io.github.symiku.obcreader;

import android.content.Context;
import android.content.Intent;
import android.net.ConnectivityManager;
import androidx.test.core.app.ApplicationProvider;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import static org.junit.Assert.*;

@RunWith(AndroidJUnit4.class)
public class OnlineImportTest extends DeviceTestBase {
    @Test public void onlineSearchAndRefreshPreserveReadingState() throws Exception {
        Context context = ApplicationProvider.getApplicationContext();
        ConnectivityManager connectivity = (ConnectivityManager) context.getSystemService(Context.CONNECTIVITY_SERVICE);
        long deadline = System.currentTimeMillis() + 60000;
        while (connectivity.getActiveNetwork() == null && System.currentTimeMillis() < deadline) Thread.sleep(500);
        assertNotNull("Online test requires emulator network", connectivity.getActiveNetwork());
        activity.launchActivity(new Intent(context, MainActivity.class));
        await("document.querySelectorAll('#results .card').length > 0");
        JSONObject before = api("GET", "/api/entry/763", "");
        String title = before.getString("title");
        assertTrue(api("GET", "/api/remote?q=" + java.net.URLEncoder.encode(title, "UTF-8"), "").getJSONArray("items").length() > 0);
        api("POST", "/api/read", "{\"id\":\"763\",\"is_read\":true}");
        JSONObject updated = api("POST", "/api/import", "{\"id\":\"763\",\"refresh\":true}");
        assertEquals("763", updated.getString("id"));
        assertTrue(updated.getJSONArray("sections").length() > 0);
        assertTrue(updated.getBoolean("is_read"));
        // Verify the newly downloaded text immediately remains usable without network.
        device.executeShellCommand("svc wifi disable");
        device.executeShellCommand("svc data disable");
        device.executeShellCommand("cmd connectivity airplane-mode enable");
        deadline = System.currentTimeMillis() + 10000;
        while (connectivity.getActiveNetwork() != null && System.currentTimeMillis() < deadline) Thread.sleep(200);
        assertNull(connectivity.getActiveNetwork());
        assertEquals(updated.getJSONArray("sections").toString(), api("GET", "/api/entry/763", "").getJSONArray("sections").toString());
        asyncJs("navigate('#entry/763');");
        await("current && current.id === '763' && document.getElementById('article').textContent.length > 0");
    }
}
