# Contributing to aiozoneminder

Bug reports and pull requests are welcome.

## Development

```bash
pip install -e '.[test,lint]'
ruff check . && ruff format --check .
mypy
pytest --cov
```

These are the checks CI runs. Add or update a test with every change.

### Live tests against your own server

`tests/live/` runs the client against a real ZoneMinder, over each API you
configure. It is skipped unless you set at least one URL and a user:

```bash
export ZM_LIVE_V2_URL=http://zm.local/zm      # API v2 (built in)
export ZM_LIVE_V3_URL=http://zm.local:8080    # API v3 (zm-api)
export ZM_LIVE_USER=admin ZM_LIVE_PASSWORD=secret
pytest tests/live -rsxX
```

Optional: `ZM_LIVE_TIMEZONE` (the server's zone, for API v2 times),
`ZM_LIVE_MONITOR` (the monitor id to use; by default the first capturing one,
preferring one with PTZ), and `ZM_LIVE_RESTRICTED_USER` /
`ZM_LIVE_RESTRICTED_PASSWORD` (a user without System view, for the permission
checks).

By default the tests only read. `ZM_LIVE_WRITE=1` adds the ones that change the
server: monitor modes, capturing, forced alarms, PTZ, and saving and switching
run states. They put back what they change (modes and the active run state are
restored, alarms cancelled, `aiozm-live-*` run states deleted), but forced
alarms leave events behind and the token tests log out every session of the
user. Use a test server, or at least a dedicated user. A full run takes about
five minutes; one test waits two minutes for zm-api to end an idle live
session.

Tests for bugs fixed by open pull requests are marked `xfail` with the PR's
title, so they show as XFAIL without the fix and XPASS with it. The module
docstring in `tests/live/__init__.py` lists what the live tests leave out, and
why.

## License and CLA

The project is licensed under **Apache-2.0**. Before a pull request can be
merged, you need to agree to the [Contributor License Agreement](CLA.md). You
keep the copyright in your work. The CLA gives ZoneMinder Inc a licence to use
it, including the right to offer the project under other terms in future.

The CLA Assistant check does this for you. On your first pull request a bot
asks you to sign by replying with:

> I have read the CLA Document and I hereby sign the CLA

You only sign once.
