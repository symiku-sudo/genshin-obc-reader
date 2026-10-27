package io.github.symiku.obcreader;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.*;
import android.widget.TextView;
import androidx.webkit.WebViewAssetLoader;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import org.json.JSONObject;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.zip.GZIPInputStream;

public class MainActivity extends Activity {
    private static final String ORIGIN = "https://appassets.androidplatform.net";
    private static final ExecutorService IO = Executors.newFixedThreadPool(3);
    private static final Object INIT = new Object();
    private static boolean ready;
    WebView web;
    volatile String startupError;
    private ValueCallback<Uri[]> fileCallback;
    private String saveId, saveData;

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        TextView loading = new TextView(this);
        loading.setText("正在准备本地文本库…\n首次启动需要解压文本，请稍候。");
        loading.setPadding(32, 80, 32, 32);
        setContentView(loading);
        IO.execute(() -> {
            try {
                synchronized (INIT) {
                    if (!ready) {
                        android.util.Log.i("OBCStartup", "Installing bundled corpus");
                        installCorpus();
                        android.util.Log.i("OBCStartup", "Corpus verified; copying resources");
                        copyAssets("resources", new File(getFilesDir(), "resources"));
                        android.util.Log.i("OBCStartup", "Starting embedded Python");
                        if (!Python.isStarted()) Python.start(new AndroidPlatform(getApplicationContext()));
                        Python.getInstance().getModule("android_runtime").callAttr("initialize", getFilesDir().getPath(), new File(getFilesDir(), "resources").getPath());
                        ready = true;
                        android.util.Log.i("OBCStartup", "Local database ready");
                    }
                }
                runOnUiThread(() -> { if (!isDestroyed()) showReader(); });
            } catch (Exception e) {
                startupError = e.toString();
                android.util.Log.e("OBCStartup", "Initialization failed", e);
                runOnUiThread(() -> loading.setText("无法准备文本库：" + e.getMessage() + "\n请检查可用存储空间后重新打开。"));
            }
        });
    }

    private void installCorpus() throws Exception {
        File database = new File(getFilesDir(), "library.sqlite3");
        if (database.exists()) return;
        JSONObject manifest;
        try (InputStream in = getAssets().open("corpus.json")) {
            manifest = new JSONObject(new String(readAll(in), StandardCharsets.UTF_8));
        }
        File staging = new File(getFilesDir(), "library.installing");
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        long count = 0;
        try (InputStream in = new GZIPInputStream(getAssets().open("library.sqlite3.gz")); OutputStream out = new FileOutputStream(staging)) {
            byte[] block = new byte[65536]; int size;
            while ((size = in.read(block)) != -1) { out.write(block, 0, size); digest.update(block, 0, size); count += size; }
        }
        StringBuilder hash = new StringBuilder();
        for (byte b : digest.digest()) hash.append(String.format("%02x", b & 255));
        if (count != manifest.getLong("bytes") || !hash.toString().equals(manifest.getString("sha256"))) {
            staging.delete(); throw new IOException("内置文本库校验失败");
        }
        if (!staging.renameTo(database)) throw new IOException("无法保存本地数据库");
    }

    private static byte[] readAll(InputStream in) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buffer = new byte[8192]; int n;
        while ((n = in.read(buffer)) != -1) out.write(buffer, 0, n);
        return out.toByteArray();
    }

    private void copyAssets(String path, File target) throws IOException {
        String[] children = getAssets().list(path);
        if (children != null && children.length > 0) {
            if (!target.isDirectory() && !target.mkdirs()) throw new IOException("无法创建资源目录");
            for (String child : children) copyAssets(path + "/" + child, new File(target, child));
        } else {
            try (InputStream in = getAssets().open(path); OutputStream out = new FileOutputStream(target)) { out.write(readAll(in)); }
        }
    }

    @SuppressWarnings("SetJavaScriptEnabled")
    private void showReader() {
        web = new WebView(this);
        web.setId(android.R.id.content);
        web.getSettings().setJavaScriptEnabled(true);
        web.getSettings().setDomStorageEnabled(true);
        web.getSettings().setAllowFileAccess(false);
        web.getSettings().setAllowContentAccess(true);
        web.getSettings().setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        web.addJavascriptInterface(new Bridge(), "ReaderNative");
        WebViewAssetLoader loader = new WebViewAssetLoader.Builder()
            .addPathHandler("/", new WebViewAssetLoader.AssetsPathHandler(this)).build();
        web.setWebViewClient(new WebViewClient() {
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                WebResourceResponse response = loader.shouldInterceptRequest(request.getUrl());
                if (response != null) return response;
                return new WebResourceResponse("text/plain", "UTF-8", 403, "Forbidden", null, new ByteArrayInputStream(new byte[0]));
            }
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if (uri.toString().startsWith(ORIGIN + "/web/")) return false;
                if (request.isForMainFrame() && ("https".equals(uri.getScheme()) || "http".equals(uri.getScheme()))) {
                    try { startActivity(new Intent(Intent.ACTION_VIEW, uri)); } catch (Exception ignored) { }
                }
                return true;
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("application/json").addCategory(Intent.CATEGORY_OPENABLE);
                try { startActivityForResult(intent, 10); }
                catch (Exception e) { fileCallback.onReceiveValue(null); fileCallback = null; }
                return true;
            }
        });
        web.setOnApplyWindowInsetsListener((view, insets) -> {
            view.setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(), insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom());
            return insets;
        });
        setContentView(web);
        web.loadUrl(ORIGIN + "/web/index.html");
    }

    private void reply(String id, String json) {
        runOnUiThread(() -> {
            if (web != null && !isDestroyed()) web.evaluateJavascript("window.readerNativeResult(" + JSONObject.quote(id) + "," + json + ")", null);
        });
    }
    private void fail(String id, String message) { reply(id, "{\"error\":" + JSONObject.quote(message) + "}"); }

    private class Bridge {
        @JavascriptInterface public void request(String id, String method, String path, String body) {
            IO.execute(() -> {
                try { reply(id, Python.getInstance().getModule("android_runtime").callAttr("request", method, path, body).toString()); }
                catch (Exception e) { fail(id, "本地操作失败：" + e.getMessage()); }
            });
        }
        @JavascriptInterface public void saveDocument(String id, String name, String data) {
            runOnUiThread(() -> {
                if (saveId != null) { fail(id, "已有文件正在保存"); return; }
                if (data.length() > 2_000_000) { fail(id, "备份文件过大"); return; }
                saveId = id; saveData = data;
                try {
                    startActivityForResult(new Intent(Intent.ACTION_CREATE_DOCUMENT).setType("application/json")
                        .addCategory(Intent.CATEGORY_OPENABLE).putExtra(Intent.EXTRA_TITLE, name), 11);
                } catch (Exception e) { fail(id, "无法打开文件保存器"); saveId = null; saveData = null; }
            });
        }
    }
    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        Uri uri = result == RESULT_OK && data != null ? data.getData() : null;
        if (request == 10 && fileCallback != null) {
            fileCallback.onReceiveValue(uri == null ? null : new Uri[]{uri}); fileCallback = null;
        } else if (request == 11 && saveId != null) {
            String id = saveId, text = saveData; saveId = null; saveData = null;
            if (uri == null) { fail(id, "已取消保存"); return; }
            IO.execute(() -> {
                try (OutputStream out = getContentResolver().openOutputStream(uri, "wt")) {
                    if (out == null) throw new IOException("无法打开文件");
                    out.write(text.getBytes(StandardCharsets.UTF_8));
                } catch (Exception e) { fail(id, "保存失败：" + e.getMessage()); return; }
                reply(id, "{\"saved\":true}");
            });
        }
    }
    @Override public void onBackPressed() {
        if (web == null) { super.onBackPressed(); return; }
        web.evaluateJavascript("window.readerBack ? readerBack() : false", value -> {
            if (!"true".equals(value)) MainActivity.super.onBackPressed();
        });
    }
    @Override protected void onPause() {
        if (web != null) web.evaluateJavascript("if(typeof remember==='function') remember()", null);
        super.onPause();
    }
    @Override protected void onDestroy() {
        if (fileCallback != null) fileCallback.onReceiveValue(null);
        if (web != null) { web.removeJavascriptInterface("ReaderNative"); web.destroy(); web = null; }
        super.onDestroy();
    }
}
