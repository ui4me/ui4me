# UI4ME

**The application-friendly entry point to [UI4ME Core](https://github.com/ui4me/ui4me-core).**

UI4ME 0.1.0 is deliberately minimal: it re-exports the stable public Python API
from `ui4me-core` without copying, subclassing or wrapping its runtime classes.
The renderer, native desktop host, events, OS integration and resource management
all remain in Core. UI4ME will add components, themes and ergonomic application
helpers in later releases.

## Usage

```python
from ui4me import Application, Window, Document, LiveBitmap

# These are the exact Core classes, not lookalikes or proxies:
from ui4me_core import Application as CoreApplication
assert Application is CoreApplication
```

No Rust code, native binaries or standalone executable are provided by this
package. It does not install an extra command-line program; the Core distribution
owns `ui4me-host` and its launcher.

## Installation

Once **`ui4me-core` has been published to PyPI**:

```bash
python -m pip install ui4me
```

Before then, use the **qualified Core wheel** for your system from the Core
project, then install this wrapper without trying to resolve an unpublished
Core package:

```bash
python -m pip install /path/to/ui4me_core-1.0.0-py3-none-PLATFORM.whl
python -m pip install -e . --no-deps
python -c 'from ui4me import Application; from ui4me_core import Application as C; assert Application is C'
```

Alternatively, after Core can be installed through the configured package
index, `python -m pip install .` resolves its dependency automatically.

**Dependencies**: Python 3.10+ and `ui4me-core>=1.0.0,<2.0.0`. The Python
wrapper is cross-platform; the underlying Core wheels currently target
supported Linux and Windows environments.

## Repository ownership

- [`ui4me/ui4me-core`](https://github.com/ui4me/ui4me-core): Rust engine,
  native host, protocol, OS adapters, Python Core SDK and native wheel artifacts.
- [`ui4me/ui4me`](https://github.com/ui4me/ui4me): public developer-facing Python
  facade, future components and themes; later language-specific frontends can
  be added independently.

The legacy implementation is intentionally gone from the current tree; the
repository's Git history retains it. See [migration notes](docs/MIGRATION.md).

## Development

```bash
python -m unittest discover -s tests -v
python -m pip install --upgrade build twine
python -m build
python -m twine check dist/*
```

The unit tests use a controlled dummy Core module so the facade can be tested
before Core's first PyPI release. Run the real-Core integration test with a
qualified Core wheel installed before publishing this package.

## Publishing

A **manual-only** GitHub Actions workflow builds the pure Python wheel and
source archive and can publish using PyPI Trusted Publishing once the owner has
configured the PyPI project and explicitly enables publishing. There is no
push-triggered or tag-triggered release. See [release instructions](docs/PUBLISHING.md).
