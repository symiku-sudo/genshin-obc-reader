# Android offline parity acceptance

## Version 1.2.0 acceptance

[Successful 1.2.0 build and device acceptance](https://github.com/symiku-sudo/genshin-obc-reader/actions/runs/41570337620)
uses commit `7ffce1404db8ced41aafe88421393038c0b88388`; details are recorded in release `provenance.json`.
The published APK is copied from that build artifact without rebuilding.

- 51 Python backend tests and UI/Android bridge regressions cover section-scoped
  AND, OR (including single-character terms), 1201 keywords without SQL parameter
  limits, grouped search history, note editing, two recent readings, selected-text
  search/return, legacy backup compatibility and all new backup fields.
- OfflineTest and PersistenceTest exercise the complete offline library, actual
  `adb install -r`, process restart and retained reading records.
- ReadingFeaturesTest checks selection/highlights and exact character-anchor
  restoration during display-size changes. A viewport guard prevents scroll events
  preceding resize from overwriting the original anchor.
- Version12Test checks the actual WebView position below the status-bar inset,
  white unread buttons, 22 moon cards, note creation/editing, two recent entries,
  selected-text search/return, AND/OR history and persistence after Activity restart.
- The original corpus snapshot remains 3616 entries / 17489 sections. A verified
  supplemental file imports all text from 22 月谕圣牌 on first launch/upgrade without
  replacing existing entries or reading flags, yielding 3638 entries / 17511 sections.
- v1/v2/v3 signing remains enabled with the original certificate fingerprint listed
  below. Physical vivo and folding-device testing is not claimed.

Both live OnlineImportTest cases passed: remote title search and refresh followed
by offline reading. Transient upstream 502 responses retry up to three times, with
assertions that failed attempts retain existing text and read state. No failed or
skipped device tests are counted as passed.

## Version 1.1.0 acceptance

[Successful 1.1.0 build and device acceptance](https://github.com/symiku-sudo/genshin-obc-reader/actions/runs/40820602069)
uses commit `d60331090f4b728ec663acb9cb6e8e86e21f9006`. It passed 48 shared Python tests,
reading UI/bridge regression tests, OfflineTest, PersistenceTest, ReadingFeaturesTest,
and both OnlineImportTest cases on Android 15.

- The actual APK contains the legacy `META-INF` developer certificate. Verification
  explicitly includes API 23 to exercise v1 even though runtime minimum remains API 24;
  v1, v2 and v3 all verify. SHA-256 signer fingerprint remains
  `2d59993be66a227aff2ccb8f5beb094b5766b54d9cc3edf8ad3e65fccaa310a3`.
  This addresses missing legacy signing; resolution of vivo's reported installer
  message still requires installation on the affected physical phone.
- Device test changes display size to 1000x1400 and back, asserting the current entry
  stays open and the saved character anchor returns within 5 pixels of its target.
  It then closes/reopens the Activity and exercises the resume button and saved highlights.
  This emulates size changes; it is not a physical foldable-device test.
- UI tests cover read/unread changes with stable cards, reversing an accidental tap,
  applying the new state on explicit refilter, and the read button after the article.
- Cross-paragraph and overlapping highlights, unchanged source text, deletion,
  old backup compatibility, invalid backup rejection, and export/delete/restore of
  highlights are checked. Device tests verify highlights survive Activity restart.
- App files and preferences remain local. Original offline acceptance gates below still pass.

The test harness only dismisses the specifically identified Pixel Launcher ANR on a fresh
CI emulator; reader or document-provider ANRs remain failures.

## Version 1.0.0 release evidence

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
