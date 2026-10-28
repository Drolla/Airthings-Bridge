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

- `main` is the principal branch. Do topic work in `<topic>` branches,
  merged into `main` with `git merge --no-ff`.
- Topic branches and `main` may be committed and pushed.
- The project is forked from https://github.com/Drolla/WavePlus_Bridge
  (version 1.x), which doesn't receive the 2.0 changes.

## Checks

Install the package with its development tools (`pip install -e .[dev]`),
then before committing:

```
python -m ruff check .
python -m mypy
python -m pytest
```

Keep the documentation in `docs/` and `CHANGELOG.md` up to date.
