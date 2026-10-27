#!/usr/bin/env bash
set -euo pipefail
collect() {
  adb logcat -d > device-runtime.log || true
  adb pull /sdcard/Android/data/io.github.symiku.obcreader/files device-evidence || true
}
trap collect EXIT
adb shell svc wifi disable
adb shell svc data disable
adb shell settings put global airplane_mode_on 1
adb shell am broadcast -a android.intent.action.AIRPLANE_MODE --ez state true
adb logcat -c
gradle :app:connectedReleaseAndroidTest --stacktrace
