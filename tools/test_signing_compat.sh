#!/usr/bin/env bash
set -euo pipefail
adb install previous/obc-reader-1.3.0.apk
adb shell am start -W -n io.github.symiku.obcreader/.MainActivity
adb shell am force-stop io.github.symiku.obcreader
adb install -r repaired/obc-reader-1.3.1.apk
adb shell dumpsys package io.github.symiku.obcreader > repaired/package-verification.txt
grep -q 'versionCode=6' repaired/package-verification.txt
grep -q 'versionName=1.3.1' repaired/package-verification.txt
adb shell am start -W -n io.github.symiku.obcreader/.MainActivity
for attempt in $(seq 1 40); do
  adb shell uiautomator dump /sdcard/window.xml >/dev/null
  adb shell cat /sdcard/window.xml > repaired/window.xml
  if grep -q '观测观测枢' repaired/window.xml; then exit 0; fi
  sleep 3
done
cat repaired/window.xml
exit 1
