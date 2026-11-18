package io.github.symiku.obcreader;

import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.os.Build;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.*;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import java.util.concurrent.Executors;
import java.util.concurrent.ExecutorService;

/** Process-wide, app-private download state. No activity is retained. */
final class AppUpdater {
    static final String REPO = "https://github.com/symiku-sudo/genshin-obc-reader";
    static final String API = "https://api.github.com/repos/symiku-sudo/genshin-obc-reader/releases/latest";
    private static AppUpdater instance;
    static synchronized AppUpdater get(Context context) {
        if(instance == null) instance = new AppUpdater(context.getApplicationContext());
        return instance;
    }
    private final Context context;
    private final SharedPreferences prefs;
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private final File partial, apk;
    interface Connections {HttpURLConnection open(URL url,long offset) throws Exception;}
    private final Connections connections;
    private volatile JSONObject release;
    private volatile String phase = "idle", message = "";
    private volatile boolean busy, paused;
    private volatile long received;
    private volatile HttpURLConnection activeConnection;
    final String installedVersion;

    private AppUpdater(Context context) {
        this(context,"app-update",new File(context.getFilesDir(),"updates"),AppUpdater::open);
    }
    AppUpdater(Context context,String preferences,File directory,Connections connections) {
        this.context = context;this.connections=connections;
        prefs = context.getSharedPreferences(preferences, Context.MODE_PRIVATE);
        directory.mkdirs();partial = new File(directory,"update.part");apk = new File(directory,"update.apk");
        String version = "";
        try {version=context.getPackageManager().getPackageInfo(context.getPackageName(),0).versionName;}
        catch(Exception ignored) {}
        installedVersion=version;
        try { release = new JSONObject(prefs.getString("release", "{}")); }
        catch(Exception ignored) {release=new JSONObject();}
        if (!newer(release.optString("version"),installedVersion)) {
            partial.delete();apk.delete();release=new JSONObject();
        } else if(identity(release).equals(prefs.getString("download", ""))) {
            received=partial.length();
            // A completed file is still reverified when the user requests installation.
            if(apk.length()==release.optLong("size")&&apk.isFile())phase="ready";
            else if(received>0)phase="paused";
        }
    }
    static boolean newer(String candidate,String installed) {
        if(!candidate.matches("[0-9]{1,6}\\.[0-9]{1,6}\\.[0-9]{1,6}") || !installed.matches("[0-9]{1,6}\\.[0-9]{1,6}\\.[0-9]{1,6}"))return false;
        String[] a=candidate.split("\\."),b=installed.split("\\.");
        for(int i=0;i<3;i++){int x=Integer.parseInt(a[i]),y=Integer.parseInt(b[i]);if(x!=y)return x>y;}
        return false;
    }
    static JSONObject parseRelease(JSONObject data,String installed) throws Exception {
        if(data.optBoolean("draft")||data.optBoolean("prerelease"))throw new IOException("未找到正式版本");
        String tag=data.getString("tag_name"),version=tag.startsWith("v")?tag.substring(1):tag;
        if(!version.matches("[0-9]{1,6}\\.[0-9]{1,6}\\.[0-9]{1,6}"))throw new IOException("版本信息无效");
        if(!newer(version,installed))return new JSONObject();
        JSONArray assets=data.getJSONArray("assets");
        String expected=REPO+"/releases/download/"+tag+"/obc-reader-"+version+".apk";
        for(int i=0;i<assets.length();i++){
            JSONObject a=assets.getJSONObject(i);
            if(!a.optString("name").equals("obc-reader-"+version+".apk"))continue;
            String digest=a.optString("digest");long size=a.getLong("size");
            if(!expected.equals(a.getString("browser_download_url"))||!digest.matches("sha256:[a-fA-F0-9]{64}")||size<=0||!"uploaded".equals(a.optString("state")))throw new IOException("安装包信息不完整，请稍后重试或查看发布页");
            return new JSONObject().put("version",version).put("notes",data.optString("body"))
                .put("url",expected).put("page",REPO+"/releases/tag/"+tag).put("sha256",digest.substring(7).toLowerCase(Locale.ROOT)).put("size",size).put("asset",a.getLong("id"));
        }
        throw new IOException("该版本尚未提供 Android 安装包");
    }
    private static String identity(JSONObject item){return item.optString("asset")+":"+item.optString("sha256")+":"+item.optLong("size");}
    synchronized JSONObject status() throws Exception {
        return new JSONObject().put("installed",installedVersion).put("release",release).put("phase",phase)
            .put("message",message).put("received",phase.equals("ready")?apk.length():received).put("busy",busy);
    }
    synchronized void check(boolean manual) {
        if(busy)return;
        long elapsed=System.currentTimeMillis()-prefs.getLong("checked",0);
        if(!manual&&elapsed>=0&&elapsed<86400000L)return;
        busy=true;String previous=phase;phase="checking";message="";
        worker.execute(()->{
            try {refresh();phase=apk.isFile()?"ready":partial.length()>0?"paused":"idle";if(manual&&release.length()==0)message="当前已是最新版本";}
            catch(Exception e){phase=previous; if(manual)message="检查失败："+error(e);}
            finally{busy=false;}
        });
    }
    private void refresh() throws Exception {
        // Persist attempts, including offline attempts, to avoid repeated startup traffic.
        prefs.edit().putLong("checked",System.currentTimeMillis()).commit();
        JSONObject result;
        HttpURLConnection connection=connections.open(new URL(API),0);
        try {
            if(connection.getResponseCode()!=200)throw new IOException("GitHub 暂时无法连接（"+connection.getResponseCode()+"）");
            try(InputStream input=connection.getInputStream();ByteArrayOutputStream output=new ByteArrayOutputStream()){
                byte[] buffer=new byte[8192];int n;
                while((n=input.read(buffer))!=-1){if(output.size()+n>2000000)throw new IOException("版本信息过大");output.write(buffer,0,n);}
                result=parseRelease(new JSONObject(output.toString("UTF-8")),installedVersion);
            }
        } finally {connection.disconnect();}
        if(!identity(result).equals(prefs.getString("download",""))){
            if(!deleteDownloads())throw new IOException("无法替换旧下载，请检查存储空间");received=0;
            prefs.edit().putString("download",identity(result)).commit();
        }
        release=result;prefs.edit().putString("release",result.toString()).commit();
    }
    private boolean deleteDownloads(){return (!partial.exists()||partial.delete())&&(!apk.exists()||apk.delete());}
    synchronized void download(){
        if(busy)return;
        busy=true;paused=false;phase="checking";message="";
        worker.execute(()->{
            try {
                refresh();
                if(release.length()==0){phase="idle";message="当前已是最新版本";return;}
                if(paused){phase="paused";return;}
                if(!apk.isFile())transfer();
                if(paused){phase="paused";return;}
                phase="verifying";
                File file=apk.isFile()?apk:partial;
                try {verify(file,release);}catch(Exception e){deleteDownloads();received=0;throw e;}
                if(!apk.isFile()&&!partial.renameTo(apk))throw new IOException("无法保存安装包");
                phase="ready";
            } catch(Exception e){phase="paused";if(!paused)message="下载未完成："+error(e)+(partial.length()>0?"。已保留下载进度，可重试。":"。请重试或查看发布页。");}
            finally{activeConnection=null;busy=false;}
        });
    }
    void pause(){paused=true;HttpURLConnection c=activeConnection;if(c!=null)c.disconnect();}
    private void transfer() throws Exception {
        long total=release.getLong("size"),offset=partial.length();
        if(offset>total){if(!partial.delete())throw new IOException("无法重新下载");offset=0;}
        received=offset;
        if(offset==total)return;
        phase="downloading";
        HttpURLConnection c=connections.open(new URL(release.getString("url")),offset);activeConnection=c;
        try{
            int code=c.getResponseCode();
            if(code==200)offset=0; // Server ignored Range: replace, never append a full response.
            else if(code!=206)throw new IOException("GitHub 下载返回 "+code);
            if(code==206)validateRange(c.getHeaderField("Content-Range"),offset,total);
            long length=c.getContentLengthLong();
            if(length>=0&&length!=total-offset)throw new IOException("安装包大小已变化，请重试");
            if(partial.getParentFile().getUsableSpace()<total-offset+8L*1024*1024)throw new IOException("存储空间不足");
            received=offset;
            try(InputStream in=c.getInputStream();FileOutputStream out=new FileOutputStream(partial,offset>0)){
                byte[] buffer=new byte[65536];int n;
                while(!paused&&(n=in.read(buffer))!=-1){
                    if(received+n>total)throw new IOException("下载大小超出预期");
                    out.write(buffer,0,n);received+=n;
                }
                out.getFD().sync();
            }
            if(!paused&&received!=total)throw new IOException("网络中断");
        }finally{c.disconnect();activeConnection=null;}
    }
    static void validateRange(String header,long offset,long total) throws IOException {
        if(!("bytes "+offset+"-"+(total-1)+"/"+total).equals(header))throw new IOException("续传响应不匹配，请重试");
    }
    static HttpURLConnection open(URL initial,long offset) throws Exception {
        URL url=initial;
        for(int redirects=0;redirects<8;redirects++){
            String host=url.getHost();
            if(!"https".equals(url.getProtocol())||url.getUserInfo()!=null||!(host.equals("api.github.com")||host.equals("github.com")||host.endsWith(".githubusercontent.com")))throw new IOException("非官方更新地址");
            HttpURLConnection c=(HttpURLConnection)url.openConnection();
            c.setConnectTimeout(15000);c.setReadTimeout(20000);c.setInstanceFollowRedirects(false);
            c.setRequestProperty("User-Agent","OBC-Reader-Android");c.setRequestProperty("Accept-Encoding","identity");
            if(host.equals("api.github.com")){c.setRequestProperty("Accept","application/vnd.github+json");c.setRequestProperty("X-GitHub-Api-Version","2022-11-28");}
            if(offset>0)c.setRequestProperty("Range","bytes="+offset+"-");
            int code;
            try{code=c.getResponseCode();}catch(Exception e){c.disconnect();throw e;}
            if(code==301||code==302||code==303||code==307||code==308){String next=c.getHeaderField("Location");c.disconnect();if(next==null)throw new IOException("下载跳转无效");url=new URL(url,next);continue;}
            return c;
        }
        throw new IOException("下载跳转过多");
    }
    static String sha256(File file) throws Exception {
        MessageDigest digest=MessageDigest.getInstance("SHA-256");
        try(InputStream in=new FileInputStream(file)){byte[] b=new byte[65536];int n;while((n=in.read(b))!=-1)digest.update(b,0,n);}
        StringBuilder result=new StringBuilder();for(byte b:digest.digest())result.append(String.format(Locale.ROOT,"%02x",b&255));return result.toString();
    }
    private static Set<String> certificates(PackageInfo info){
        Signature[] signatures=Build.VERSION.SDK_INT>=28?(info.signingInfo==null?null:info.signingInfo.getApkContentsSigners()):info.signatures;
        Set<String> result=new HashSet<>();if(signatures!=null)for(Signature s:signatures)result.add(s.toCharsString());return result;
    }
    void verify(File file,JSONObject item) throws Exception {
        if(file.length()!=item.getLong("size")||!sha256(file).equals(item.getString("sha256")))throw new IOException("安装包校验失败，请重新下载");
        PackageManager pm=context.getPackageManager();int flags=Build.VERSION.SDK_INT>=28?PackageManager.GET_SIGNING_CERTIFICATES:PackageManager.GET_SIGNATURES;
        PackageInfo archive=pm.getPackageArchiveInfo(file.getPath(),flags),own=pm.getPackageInfo(context.getPackageName(),flags);
        if(archive==null||!context.getPackageName().equals(archive.packageName)||!item.getString("version").equals(archive.versionName))throw new IOException("安装包身份不符");
        long remote=Build.VERSION.SDK_INT>=28?archive.getLongVersionCode():archive.versionCode;
        long local=Build.VERSION.SDK_INT>=28?own.getLongVersionCode():own.versionCode;
        if(remote<=local)throw new IOException("安装包不是较新版本");
        Set<String> expected=certificates(own);
        if(expected.isEmpty()||!expected.equals(certificates(archive)))throw new IOException("安装包签名不符");
    }
    interface Installer {void ready(File file);void failed(String message);}
    synchronized void install(Installer callback){
        if(busy){callback.failed("请等待当前更新操作完成");return;}
        if(!"ready".equals(phase)){callback.failed("请先完成下载");return;}
        busy=true;phase="verifying";
        worker.execute(()->{
            try{verify(apk,release);phase="ready";callback.ready(apk);}
            catch(Exception e){deleteDownloads();received=0;phase="paused";message="安装校验失败："+error(e);callback.failed(message);}
            finally{busy=false;}
        });
    }
    private static String error(Exception e){return e.getMessage()==null?"连接中断":e.getMessage();}
}
