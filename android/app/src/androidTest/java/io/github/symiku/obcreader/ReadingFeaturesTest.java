package io.github.symiku.obcreader;

import android.content.Intent;
import androidx.test.core.app.ApplicationProvider;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import org.junit.Test;
import org.junit.runner.RunWith;
import static org.junit.Assert.*;

@RunWith(AndroidJUnit4.class)
public class ReadingFeaturesTest extends DeviceTestBase {
    @Test public void selectionResumeAndScreenSizeContinuity() throws Exception {
        ensureOffline();
        activity.launchActivity(new Intent(ApplicationProvider.getApplicationContext(), MainActivity.class));
        await("document.querySelectorAll('#results .card').length > 0");
        asyncJs("document.getElementById('read-filter').value='unread'; await localSearch();window.testCard=document.querySelector('#results [data-read-id]');window.testCardId=testCard.dataset.readId;testCard.click();");
        await("testCard.getAttribute('aria-pressed')==='true' && !testCard.disabled");
        check("testCard.isConnected");
        js("testCard.click();true");
        await("testCard.getAttribute('aria-pressed')==='false' && !testCard.disabled");
        js("activeTerms=[];navigate('#entry/1600');true");
        await("current && current.id==='1600' && document.querySelector('#article section > p:not(.section-meta)')!==null");
        check("Boolean(document.getElementById('article').compareDocumentPosition(document.getElementById('mark-read')) & Node.DOCUMENT_POSITION_FOLLOWING)");
        js("window.testNotesBefore=highlights.length;window.testParagraph=prose().find(p=>p.textContent.length>20);const r=characterRange(testParagraph,2,12);window.getSelection().removeAllRanges();window.getSelection().addRange(r);document.dispatchEvent(new Event('selectionchange'));true");
        await("!document.getElementById('selection-tools').hidden");
        js("document.getElementById('save-highlight').click();true");
        await("highlights.length===testNotesBefore+1 && document.querySelector('#article mark.user-highlight')!==null");
        js("window.scrollTo(0,1000);remember();true");
        await("readingAnchors['1600'] && positions['1600']>0");
        String quote = js("readingAnchors['1600'].quote");
        try {
            device.executeShellCommand("wm size 1000x1400");
            Thread.sleep(1500);
            await("current && current.id==='1600' && !window.readingLayoutPending");
            assertEquals(quote,js("readingAnchors['1600'].quote"));
            check("Math.abs(characterRange(anchorParagraph(readingAnchors['1600']),readingAnchors['1600'].offset).getBoundingClientRect().top-readingTop()-readingAnchors['1600'].top)<5");
        } finally {
            device.executeShellCommand("wm size reset");
        }
        Thread.sleep(1500);
        await("current && current.id==='1600' && !window.readingLayoutPending");
        js("remember();true");
        String anchor = js("JSON.stringify(readingAnchors['1600'])");
        activity.finishActivity();
        activity.launchActivity(new Intent(ApplicationProvider.getApplicationContext(), MainActivity.class));
        await("!document.getElementById('resume-reading').hidden");
        js("document.getElementById('resume-reading').click();true");
        await("current && current.id==='1600' && document.querySelector('#article mark.user-highlight')!==null");
        check("Math.abs(characterRange(anchorParagraph(readingAnchors['1600']),readingAnchors['1600'].offset).getBoundingClientRect().top-readingTop()-readingAnchors['1600'].top)<5");
        js("document.getElementById('open-highlights').click();true");
        await("document.querySelectorAll('#highlights-list .highlight-card').length>0");
        check("document.getElementById('highlights-list').textContent.includes('查看原文')");
    }
}
