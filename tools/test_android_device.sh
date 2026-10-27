#!/usr/bin/env bash
set -euo pipefail
collect() {
  adb logcat -d > device-runtime.log || true
  adb pull /sdcard/Android/data/io.github.symiku.obcreader/files device-evidence || true
}
trap collect EXIT
adb shell svc wifi disable
adb shell svc data disable
adb shell cmd connectivity airplane-mode enable
adb logcat -c
gradle :app:assembleReleaseAndroidTest --stacktrace
adb install -r app/build/outputs/apk/release/app-release.apk
adb install -r app/build/outputs/apk/androidTest/release/app-release-androidTest.apk
# Keep the app installed so its screenshots and state survive the test run.
adb shell am instrument -w -r -e class io.github.symiku.obcreader.OfflineTest \
  io.github.symiku.obcreader.test/androidx.test.runner.AndroidJUnitRunner | tee device-tests.log
grep -Eq '^OK \([1-9][0-9]* tests?\)' device-tests.log
