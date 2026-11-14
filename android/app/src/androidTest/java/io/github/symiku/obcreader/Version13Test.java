package io.github.symiku.obcreader;

import android.content.Intent;
import androidx.test.core.app.ApplicationProvider;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import static org.junit.Assert.*;

@RunWith(AndroidJUnit4.class)
public class Version13Test extends DeviceTestBase {
    @Test public void taskCorpusFiltersBranchesAndBackupWorkOffline() throws Exception {
        ensureOffline();
        activity.launchActivity(new Intent(ApplicationProvider.getApplicationContext(), MainActivity.class));
        await("document.querySelectorAll('#results .card').length > 0");
        for (String category : new String[]{"魔神任务", "世界任务", "传说任务", "邀约任务", "限时任务"}) {
            JSONObject result = api("GET", "/api/search?category=" + java.net.URLEncoder.encode(category, "UTF-8"), "");
            assertTrue("No offline entries for " + category, result.getInt("total") > 0);
        }
        js("location.hash='#entry/399'; true");
        await("document.querySelector('#article .task-branches a') !== null");
        check("document.querySelectorAll('#toc-links details').length > 0");
        js("window.branchTarget=document.querySelector('#article .task-branches a').getAttribute('href'); document.querySelector('#article .task-branches a').click(); true");
        await("!document.getElementById('reader').hidden && location.hash===window.branchTarget && document.querySelectorAll('#article section').length>0");
        js("location.hash='#entry/1727'; true");
        await("!document.getElementById('task-missing').hidden && document.getElementById('reader-title').textContent.includes('芭芭拉')");
        check("document.getElementById('warnings').textContent.includes('正文不完整')");
        check("document.getElementById('reader-title').textContent.startsWith('【缺失】')");
        check("!!validateBackup({format:'obc-reading-backup',version:1,read_entries:[],bookmarks:[],positions:{},font:18,anchors:{'1727':{section:document.querySelector('#article section').id,paragraph:0,offset:0,top:0,quote:''}}})");
    }
}
