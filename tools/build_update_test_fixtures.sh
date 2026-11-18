#!/usr/bin/env bash
# Tiny APKs used only by instrumentation to verify package/version/signing checks.
set -euo pipefail
fixture_dir=$(mktemp -d)
trap 'rm -rf "$fixture_dir"' EXIT
fixture_assets=android/app/src/androidTest/assets
mkdir -p "$fixture_assets"
cat > "$fixture_dir/AndroidManifest.xml" <<'XML'
<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="io.github.symiku.obcreader" android:versionCode="7" android:versionName="1.3.2"><uses-sdk android:minSdkVersion="24" android:targetSdkVersion="35"/><application android:label="Update verification fixture" android:hasCode="false"/></manifest>
XML
"$ANDROID_HOME/build-tools/35.0.0/aapt2" link -I "$ANDROID_HOME/platforms/android-35/android.jar" --manifest "$fixture_dir/AndroidManifest.xml" -o "$fixture_dir/unsigned.apk"
"$ANDROID_HOME/build-tools/35.0.0/apksigner" sign --ks "$OBC_SIGNING_FILE" --ks-key-alias reader --ks-pass env:OBC_SIGNING_PASSWORD --out "$fixture_assets/update-valid.apk" "$fixture_dir/unsigned.apk"
keytool -genkeypair -keystore "$fixture_dir/wrong.p12" -storepass fixture-only -keypass fixture-only -alias wrong -dname CN=Test -keyalg RSA -validity 2 >/dev/null 2>&1
"$ANDROID_HOME/build-tools/35.0.0/apksigner" sign --ks "$fixture_dir/wrong.p12" --ks-pass pass:fixture-only --out "$fixture_assets/update-wrong-signer.apk" "$fixture_dir/unsigned.apk"
