# Android offline parity acceptance

## Release evidence

Version 1.0.0 is built from commit `ff25868780a12df8d839191b0eaee9b6b8daaa18`.
[Successful build and device acceptance](https://github.com/symiku-sudo/genshin-obc-reader/actions/runs/40652630508)
ran on 2026-10-28 using an Android 15 (API 35) x86_64 emulator.
The APK includes arm64-v8a and x86_64 runtimes. Physical-device testing is not claimed.

The app runs independently of Termux, a web server, and network access. The
website remains the canonical UI; Android generates assets from it at build time.
The Python API is shared, embedded with Chaquopy, and uses private SQLite storage.

| Requirement | Evidence and result |
| --- | --- |
| Fresh offline launch with the full existing Chinese corpus | OfflineTest asserts no active network and 3616 entries / 17489 sections; passed. APK verifier checks the decompressed database against its SHA-256 and size. |
| Browse all categories and text types, pagination | OfflineTest exercises every category/type through the real WebView bridge and page controls; passed. |
| Search, exact phrases, all words, snippets, paragraph navigation | Device test searches actual title/body text, checks highlights and follows snippet links. Shared search tests cover phrase/word modes, punctuation, multiple paragraphs and stable paging; passed. |
| Read/unread, favorites and filters | Device test changes records through UI, verifies database state and filter totals; passed. |
| Font size and scroll restoration | Device test changes preferences and scrolls; PersistenceTest verifies exact storage values and restored scroll position after process death and replacement install; passed. |
| Native Back and accessible controls | Device test closes management with Android Back, returns from sample reader, and operates real document pickers. Insets and keyboard resizing are configured in MainActivity/manifest; emulator screenshots retained. |
| Same JSON backup as the website | Device test saves through Android DocumentsUI, removes records, opens the saved file and restores read/favorite state; invalid file and save cancellation preserve state; passed. Shared backup tests validate merge semantics. |
| Offline management and samples | Device test loads seven management categories, unsupported-category notices, history/details/review filter and bundled sample reader; passed. Fixtures are packaged locally. |
| Online import/update | Two device tests perform real upstream title search and cache refresh, preserve read state, then disable network and verify identical cached text; passed. Shared worker tests cover new imports, idempotency, pause/resume, failed-item retry and retention of existing cache. |
| Interrupted jobs and upgrades | Process is force-stopped and the signed APK installed with `adb install -r`; PersistenceTest verifies database/preferences survive and interrupted jobs recover as paused; passed. |
| Independent interpreter and database | Tests run the embedded Python and WebView against the app-private SQLite database, with Android connectivity explicitly disabled for offline tests. No mocked device API or localhost server. |
| Installable signed APK | CI verifies APK contents, signature and 16 KB zip alignment; passed. Final APK and SHA-256 are distributed in the v1.0.0 release. Persistent signing key is retained privately for upgrades. |

CI passed 48 shared Python tests, OfflineTest (1), PersistenceTest (1), and
OnlineImportTest (2). Device logs and screenshots are in the `android-test-results`
artifact of the linked run; APK and checksum are in `obc-reader-release`.
The release copies that tested APK without rebuilding it. Later documentation
commits do not change its application source.

## Data and scope

Current exclusions match the website: unsupported upstream categories and known
malformed upstream text blocks remain explicitly reported, never guessed.
The app includes the existing corpus; this is not a claim that every upstream
Genshin text is available. New or refreshed upstream text requires a connection.

Build inputs: the private GitHub release `android-corpus-v1` stores the compressed
SQLite snapshot and its manifest, outside Git history. Personal reading flags are
removed from this snapshot; browser reading preferences transfer through the
existing JSON backup. The APK itself contains the full text database.

The app-private database is not overwritten on upgrade. Reading backups contain
read flags, favorites, positions and font preference, not the text corpus.
Keep the same signing key and application ID when releasing updates; uninstalling
or clearing app data removes local records.
