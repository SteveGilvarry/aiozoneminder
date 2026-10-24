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

## License and CLA

The project is licensed under **Apache-2.0**. Before a pull request can be
merged, you need to agree to the [Contributor License Agreement](CLA.md). You
keep the copyright in your work. The CLA gives ZoneMinder Inc a licence to use
it, including the right to offer the project under other terms in future.

The CLA Assistant check does this for you. On your first pull request a bot
asks you to sign by replying with:

> I have read the CLA Document and I hereby sign the CLA

You only sign once.
