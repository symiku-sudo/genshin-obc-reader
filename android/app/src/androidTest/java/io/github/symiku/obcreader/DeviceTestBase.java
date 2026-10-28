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

public abstract class DeviceTestBase {
    @Rule public ActivityTestRule<MainActivity> activity = new ActivityTestRule<>(MainActivity.class, false, false);

    protected String js(String expression) throws Exception {
        CountDownLatch done = new CountDownLatch(1);
        AtomicReference<String> value = new AtomicReference<>();
        InstrumentationRegistry.getInstrumentation().runOnMainSync(() -> {
            if (activity.getActivity().web == null) { value.set("null"); done.countDown(); return; }
            activity.getActivity().web.evaluateJavascript(expression, result -> { value.set(result); done.countDown(); });
        });
        assertTrue(done.await(10, TimeUnit.SECONDS));
        return value.get();
    }
    protected void await(String expression) throws Exception {
        long deadline = System.currentTimeMillis() + 180000;
        while (System.currentTimeMillis() < deadline) {
            assertNull("Native startup failure", activity.getActivity().startupError);
            if ("true".equals(js(expression))) return;
            Thread.sleep(300);
        }
        fail("WebView condition timed out: " + expression);
    }
    protected JSONObject api(String method, String path, String body) throws Exception {
        JSONObject result = new JSONObject(Python.getInstance().getModule("android_runtime").callAttr("request", method, path, body).toString());
        assertEquals(result.toString(), 200, result.getInt("status"));
        return result.getJSONObject("data");
    }

    protected void asyncJs(String expression) throws Exception {
        js("window.testDone=false; window.testError=null; Promise.resolve().then(async()=>{" + expression + "}).then(()=>window.testDone=true,e=>{window.testError=String(e);window.testDone=true}); true");
        await("window.testDone === true");
        assertEquals("null", js("window.testError"));
    }
    protected void check(String expression) throws Exception { assertEquals(expression, "true", js(expression)); }
    protected final UiDevice device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation());
    protected UiObject2 systemText(String expression) {
        UiObject2 object = device.wait(Until.findObject(By.text(java.util.regex.Pattern.compile(expression))), 15000);
        assertNotNull("System document control: " + expression, object);
        return object;
    }
    @After public void captureScreen() throws Exception {
        File directory = ApplicationProvider.getApplicationContext().getExternalFilesDir(null);
        device.takeScreenshot(new File(directory, getClass().getSimpleName()+"-screen.png"));
        device.dumpWindowHierarchy(new File(directory, getClass().getSimpleName()+"-window.xml"));
    }

}
