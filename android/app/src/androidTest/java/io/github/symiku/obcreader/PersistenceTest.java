package io.github.symiku.obcreader;

import android.content.Context;
import android.content.Intent;
import android.net.ConnectivityManager;
import androidx.test.core.app.ApplicationProvider;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import org.json.JSONObject;
import org.json.JSONTokener;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.io.File;
import java.nio.file.Files;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;
import static org.junit.Assert.*;

@RunWith(AndroidJUnit4.class)
public class PersistenceTest extends DeviceTestBase {
    @Test public void recordsSurviveProcessDeathAndReplacementInstall() throws Exception {
        Context context = ApplicationProvider.getApplicationContext();
        ensureOffline();
        JSONObject expected = new JSONObject(new String(Files.readAllBytes(new File(context.getFilesDir(), "test-expected.json").toPath()), StandardCharsets.UTF_8));
        activity.launchActivity(new Intent(context, MainActivity.class));
        await("document.querySelectorAll('#results .card').length > 0");
        assertEquals(3616, api("GET", "/api/stats", "").getInt("entries"));
        for (String key : new String[]{"font", "positions", "bookmarks"}) {
            assertEquals("Preserved " + key, expected.getString(key), js("localStorage.getItem('obc-"+key+"')"));
        }
        assertEquals(expected.getString("reading"), api("GET", "/api/reading-backup", "").getJSONArray("read_entries").toString());
        assertEquals("paused", api("GET", "/api/job?id="+expected.getString("interrupted_job"), "").getString("state"));
        JSONObject positions = new JSONObject(new JSONTokener(expected.getString("positions")).nextValue().toString());
        String target = null;
        double offset = 0;
        for (Iterator<String> keys = positions.keys(); keys.hasNext();) {
            String key = keys.next();
            if (positions.getDouble(key) > offset) { offset = positions.getDouble(key); target = key; }
        }
        assertNotNull("First phase must record a scrolled reader", target);
        js("navigate('#entry/"+target+"');true");
        await("current && current.id === '"+target+"' && Math.abs(window.scrollY-"+offset+") < 3");
        check("document.getElementById('article').classList.contains('size-'+fontSize)");
    }
}
