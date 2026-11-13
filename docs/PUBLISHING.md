# UI4ME Python facade — manual publishing

## Dependency order

First publish and verify `ui4me-core` version **1.0.0** (Linux and Windows
wheels, source archive). Only then publish `ui4me` version **0.1.0** to PyPI.
Ordinary `pip install ui4me` cannot resolve the dependency until Core is
available on a package index or is already installed appropriately.

Both GitHub repositories can be pushed immediately; **GitHub push is not PyPI
publication**.

## Local build

```bash
python -m pip install --upgrade build twine
python -m unittest discover -s tests -v
python -m build
python -m twine check dist/*
```

The facade wheel should have a `py3-none-any` tag because it contains only
portable Python code, unlike the Core distribution that contains an ELF/EXE.
Verify its `Requires-Dist` metadata includes `ui4me-core>=1.0.0,<2.0.0`.

## GitHub Actions (manual only)

Open the `Publish UI4ME Python` workflow and choose **Run workflow**. Leave
`publish_to_pypi` unchecked to build/test and download artifacts. When Core has
been published and the PyPI project/ownership are configured, deliberately
check the publish option and run the workflow again.

PyPI Trusted Publisher configuration: owner `ui4me`, repository `ui4me`,
workflow `publish-python.yml`, environment `pypi`. Configure this via the PyPI
project (or the pending-publisher form if creating the project).

The publish job also refuses to upload unless PyPI already contains
`ui4me-core==1.0.0` with Linux and Windows wheels and an sdist, and the exact
UI4ME facade version is not already published. That check fails closed on a
network error.

No long-lived API tokens, stored passwords or automatic tag pushes are needed.
Do not reuse Core's release wheels in this repository: this package declares
Core as an external dependency and ships no native binary.

Never publish from an unreviewed reset commit or before `ui4me-core` can be
installed through a package index. Never overwrite published version numbers.
