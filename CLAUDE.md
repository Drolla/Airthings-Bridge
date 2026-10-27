# Airthings Bridge - project instructions

## Code

- Python 3.11 or later. Use 3.11 idioms and type hints on functions and
  methods (`str | None`, `list[str]`).
- Respect PEP 8, with lines of at most 100 characters, and PEP 257
  docstrings. Match the style of the surrounding code.
- Keep comments and docstrings concise. Don't state what the code already
  makes evident; comment the why and non-obvious facts. Correct comments,
  don't expand them.
- The code is the `airthings_bridge` package; the console script is
  `airthings-bridge` (`airthings_bridge.cli:main`).
- `airthings_bridge/logdb.py` is a verbatim copy of the phc logdb module
  (https://github.com/Drolla/phc/tree/main/phc/extensions/logdb), and
  `tests/test_logdb.py` of its tests. The only local changes are the module
  and logger names. Fix logdb in phc and copy it over; put bridge-specific
  behaviour into `airthings_bridge/consumers/sensorlog.py`.
- Single asyncio event loop: all I/O uses async libraries (bleak, aiohttp,
  aiomqtt, aiosmtplib); no threads. Only the vendored logdb runs blocking on
  the loop. The service runs without root.
- The `/eval` HTTP endpoint is kept, but only active in developer mode.

## Branches

- Do all work on branches. `version-2.0.0` is the principal branch; topic
  work goes into `version-2.0.0-<topic>` sub-branches that are merged into
  it with `git merge --no-ff`.
- These branches may be committed and pushed. Never merge into
  `master`/`main`.

## Checks

Install the package with its development tools (`pip install -e .[dev]`),
then before committing:

```
python -m ruff check .
python -m pytest
```
