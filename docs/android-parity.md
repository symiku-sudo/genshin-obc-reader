# Android offline parity acceptance

The APK must run independently of Termux, a web server, and network access. The
website remains the canonical UI; Android generates assets from it at build time.
The Python API is shared, embedded with Chaquopy, and uses private SQLite storage.

Required acceptance gates (not yet verified on Android):
- Fresh install in airplane mode opens the complete bundled corpus (3616 entries,
  17489 sections), with no download and no localhost service.
- All seven categories, browse pagination, text-type filters, phrase/all-word
  search, snippets and paragraph navigation work offline.
- Read/unread changes, favorite filters, font size and reading position persist
  across app restart, and remain independent of cache updates.
- Native Back closes management before returning from reader; keyboard and
  screen insets leave controls accessible.
- Export uses Android document storage; import validates and merges the same
  JSON backup as the website. Cancellation and invalid files preserve data.
- Sample imports, import history/details and existing cached entries work offline.
- Online search, new cache import, refresh, job pause/resume/retry/recheck work
  when connected; failures retain existing text and reading state. Interrupted
  jobs recover as paused after process death.
- Updates preserve the installed database and reading preferences.
- Automated Android instrumentation exercises the real embedded interpreter,
  WebView and database with device networking disabled, not mocked API responses.
- Deliver an installable APK and its checksum; retain stable signing for upgrades.

Current exclusions match the website: unsupported upstream categories and known
malformed upstream text blocks remain explicitly reported, never guessed.

Build inputs: the private GitHub release `android-corpus-v1` stores the compressed
SQLite snapshot and its manifest, outside Git history. Personal reading flags are
removed from this snapshot; browser reading preferences transfer through the
existing JSON backup. The APK itself contains the full text database.
