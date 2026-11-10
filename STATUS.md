# Foundation status

Release qualification is pending. The current source has been built and exercised
locally, but unit or headless results do not establish desktop acceptance. Use
`python dev.py report` for results tied to the current source and, when provided,
the exact candidate manifest. The report distinguishes missing, blocked, failed,
interrupted and passed observations.

The native renderer supports a deliberately small HTML subset and inline color
properties; it is not a browser. Full CSS layout, accessibility, IME and text
shaping remain outside this foundation. Windows and Linux desktop acceptance,
installed final artifacts, and the complete F01–F12 matrix are required before
calling a release qualified. CI must run on the repository, and registry setup
and publication are separate owner actions. No package has been published by
this development effort.

See [development](docs/development.md), [testing](docs/testing.md), and
[publishing](docs/publishing.md).
