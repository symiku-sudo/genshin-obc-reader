package io.github.symiku.obcreader;

import android.content.Intent;
import android.view.WindowInsets;
import androidx.test.core.app.ApplicationProvider;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import org.junit.Test;
import org.junit.runner.RunWith;
import static org.junit.Assert.*;

@RunWith(AndroidJUnit4.class)
public class Version12Test extends DeviceTestBase {
    @Test public void notesHistoryTwoResumeAndSystemInsets() throws Exception {
        ensureOffline();
        activity.launchActivity(new Intent(ApplicationProvider.getApplicationContext(),MainActivity.class));
        await("document.querySelectorAll('#results .card').length>0");
        InstrumentationRegistry.getInstrumentation().runOnMainSync(()->{
            int[] position=new int[2];activity.getActivity().web.getLocationOnScreen(position);
            WindowInsets insets=activity.getActivity().web.getRootWindowInsets();
            assertNotNull(insets);
            assertTrue("WebView must start below the status bar",position[1]>=insets.getInsets(WindowInsets.Type.statusBars()).top);
        });
        assertEquals(22,api("GET","/api/search?category=%E6%9C%88%E8%B0%95%E5%9C%A3%E7%89%8C","").getInt("total"));
        js("window.colorButton=document.querySelector('#results [data-read-id]');colorButton.click();true");
        await("!colorButton.disabled");
        js("colorButton.click();true");await("!colorButton.disabled");
        asyncJs("if(colorButton.getAttribute('aria-pressed')==='true')await toggleRead(colorButton.dataset.readId,false,colorButton);");
        check("getComputedStyle(colorButton).backgroundColor==='rgb(255, 255, 255)'");
        js("navigate('#entry/1600');true");await("current && current.id==='1600' && document.querySelectorAll('#article section').length>0");
        js("const p=prose().find(p=>p.textContent.length>20);const range=characterRange(p,0,2);getSelection().removeAllRanges();getSelection().addRange(range);document.dispatchEvent(new Event('selectionchange'));document.getElementById('annotate-selection').click();true");
        await("document.getElementById('note-editor').open");
        js("document.getElementById('note-text').value='设备验收笔记';document.getElementById('save-note').click();true");
        check("highlights.some(h=>h.note==='设备验收笔记')");
        js("openNoteEditor(highlights.find(h=>h.note==='设备验收笔记'));document.getElementById('note-text').value='二次编辑保存';document.getElementById('save-note').click();true");
        check("highlights.some(h=>h.note==='二次编辑保存')");
        js("navigate('#entry/763');true");await("current && current.id==='763'");
        await("recentReadings.length===2 && recentReadings[0].id==='763' && recentReadings[1].id==='1600'");
        js("const p=prose().find(p=>p.textContent.length>5);getSelection().addRange(characterRange(p,0,2));document.dispatchEvent(new Event('selectionchange'));document.getElementById('search-selection').click();true");
        await("!document.getElementById('library').hidden && !document.getElementById('selection-return').hidden");
        asyncJs("searchKeywords=['北风','高塔'];document.getElementById('query').value='';document.getElementById('match-mode').value='all';renderKeywords();saveSearchHistory();await localSearch();document.getElementById('match-mode').value='any';saveSearchHistory();await localSearch();");
        check("searchHistory.some(h=>h.mode==='all'&&h.keywords.length===2)&&searchHistory.some(h=>h.mode==='any'&&h.keywords.length===2)");
        js("document.getElementById('selection-return').click();true");await("current && current.id==='763'");
        activity.finishActivity();activity.launchActivity(new Intent(ApplicationProvider.getApplicationContext(),MainActivity.class));
        await("!document.getElementById('resume-reading-second').hidden");
        check("highlights.some(h=>h.note==='二次编辑保存') && searchHistory.some(h=>h.mode==='all'&&h.keywords.length===2)");
        check("getComputedStyle(document.getElementById('resume-reading')).backgroundColor!=='rgb(255, 255, 255)'");
    }
}
