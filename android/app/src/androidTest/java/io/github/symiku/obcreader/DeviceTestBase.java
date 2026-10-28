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
    protected void ensureOffline() throws Exception {
        device.executeShellCommand("cmd connectivity airplane-mode enable");
        device.executeShellCommand("svc wifi disable");
        device.executeShellCommand("svc data disable");
        android.net.ConnectivityManager manager = (android.net.ConnectivityManager) ApplicationProvider.getApplicationContext().getSystemService(Context.CONNECTIVITY_SERVICE);
        long deadline = System.currentTimeMillis() + 30000;
        while (manager.getActiveNetwork() != null && System.currentTimeMillis() < deadline) Thread.sleep(250);
        assertNull("Offline test network: " + manager.getNetworkCapabilities(manager.getActiveNetwork()), manager.getActiveNetwork());
    }
    protected void clickStable(androidx.test.uiautomator.BySelector selector) throws Exception {
        for (int attempt = 0; attempt < 5; attempt++) {
            try {
                UiObject2 target = device.wait(Until.findObject(selector), 5000);
                assertNotNull("Document control: " + selector, target);
                android.graphics.Rect bounds = target.getVisibleBounds();
                assertTrue(device.click(bounds.centerX(), bounds.centerY()));
                device.waitForIdle();
                return;
            } catch (androidx.test.uiautomator.StaleObjectException stale) {
                // DocumentsUI refreshes its roots asynchronously after opening the drawer.
                if (attempt == 4) throw stale;
                Thread.sleep(250);
            }
        }
    }
    protected void openDownloads() throws Exception {
        UiObject2 roots = device.wait(Until.findObject(By.desc("Show roots")), 5000);
        if (roots == null) roots = device.findObject(By.desc("Open navigation drawer"));
        if (roots != null) {
            roots.click();
            device.waitForIdle();
            // The toolbar and breadcrumb also say Downloads. Select the drawer row.
            clickStable(By.res("android:id/title").text(java.util.regex.Pattern.compile("Downloads|下载")));
            device.waitForIdle();
        }
    }
    protected void touchBackupChooser() throws Exception {
        js("document.getElementById('backup-file').scrollIntoView({block:'center'});true");
        UiObject2 label = device.wait(Until.findObject(By.textContains("选择备份文件")), 5000);
        if (label == null) label = device.wait(Until.findObject(By.descContains("选择备份文件")), 5000);
        assertNotNull("Visible backup file label", label);
        label.click();
    }
    @After public void captureScreen() throws Exception {
        File directory = ApplicationProvider.getApplicationContext().getExternalFilesDir(null);
        device.takeScreenshot(new File(directory, getClass().getSimpleName()+"-screen.png"));
        File hierarchy = new File(directory, getClass().getSimpleName()+"-window.xml");
        device.dumpWindowHierarchy(hierarchy);
        android.os.Bundle evidence = new android.os.Bundle();
        evidence.putString("stream", "\nDEVICE_UI:\n" + new String(java.nio.file.Files.readAllBytes(hierarchy.toPath()), java.nio.charset.StandardCharsets.UTF_8) + "\n");
        InstrumentationRegistry.getInstrumentation().sendStatus(2, evidence);
    }

}
