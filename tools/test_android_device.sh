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
gradle :app:connectedReleaseAndroidTest --stacktrace
