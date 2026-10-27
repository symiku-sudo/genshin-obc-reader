package io.github.symiku.obcreader;

import android.content.Context;
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

    @Test public void completeCorpusAndReadingWorkWithoutNetwork() throws Exception {
        // Workflow disables both Wi-Fi and mobile data before starting the app.
        activity.launchActivity(new Intent(ApplicationProvider.getApplicationContext(), MainActivity.class));
        await("document.querySelectorAll('#results .card').length > 0");
        JSONObject stats = api("GET", "/api/stats", "");
        assertEquals(3616, stats.getInt("entries"));
        assertEquals(17489, stats.getInt("sections"));
        assertEquals(7, api("GET", "/api/library", "").getJSONArray("categories").length());
        String id = api("GET", "/api/search", "").getJSONArray("items").getJSONObject(0).getString("id");
        api("POST", "/api/read", "{\"id\":\"" + id + "\",\"is_read\":true}");
        assertTrue(api("GET", "/api/entry/" + id, "").getBoolean("is_read"));
        assertEquals(1, api("GET", "/api/search?read=read", "").getInt("total"));
        js("document.querySelector('#results a').click(); true");
        await("document.querySelector('#article').textContent.length > 0");
        js("document.getElementById('bookmark').click(); true");
        await("JSON.parse(localStorage.getItem('obc-bookmarks')).length === 1");
        js("document.getElementById('open-management').click(); true");
        await("document.getElementById('management').open");
        assertEquals("true", js("readerBack()"));
        assertEquals("false", js("document.getElementById('management').open"));
        assertEquals("true", js("readerBack()"));
        await("!document.getElementById('library').hidden");
    }
}
