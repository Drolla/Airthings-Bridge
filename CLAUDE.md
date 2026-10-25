# WavePlus Bridge - project instructions

## Code

- Python 3.11 or later. Use 3.11 idioms and type hints on functions and
  methods (`str | None`, `list[str]`).
- Respect PEP 8 (79 columns) and PEP 257 docstrings. Match the style of the
  surrounding code.
- Keep comments and documentation concise. Correct them, don't expand them.
- `libs/logdb.py` is a verbatim copy of the phc logdb module
  (https://github.com/Drolla/phc/tree/main/phc/extensions/logdb), and
  `tests/test_logdb.py` of its tests. The only local changes are the module
  and logger names. Fix logdb in phc and copy it over; put bridge-specific
  behaviour into `libs/sensorlog.py`.
- BLE access uses bleak (asyncio) behind the synchronous `WavePlus` API in
  `libs/waveplus.py`. The service runs without root.
- The `/eval` HTTP endpoint is kept, but only active in developer mode.

## Branches

- Do all work on branches. `version-2.0.0` is the principal branch; topic
  work goes into `version-2.0.0-<topic>` sub-branches that are merged into
  it with `git merge --no-ff`.
- These branches may be committed and pushed. Never merge into
  `master`/`main`.

## Checks

Before committing:

```
python -m ruff check .
cd tests && python -m pytest
```
