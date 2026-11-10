# ui4me for Python

The Python facade needs a matching native runtime bundled in a platform wheel. A source checkout does not contain that runtime. The current reconstruction is not release-qualified; native desktop support and final packages still need acceptance testing.

```python
from ui4me import App

with App() as app:
    window = app.open('<h1>Hello</h1><button id="hello">Click me</button><p id="status">Ready</p>')
    window.on("click", lambda event: window.set_text("status", "Hello from Python"), element="hello")
    app.run()
```

The thread creating `App` owns commands, timers, windows and subscriptions. `post(callable)` and `stop()` may be called from another thread. Await posted work outside the owner thread. Callbacks run on the owner thread and must return promptly. A callback exception stops the application and is re-raised after native cleanup. An exception inside posted work is delivered to its Future.

`app.open_file(path)` reads a specific UTF-8 file. Paths are not interpreted relative to the package or executable. Package resources are available through `importlib.resources`. A `close_requested` handler returns `False` to veto a normal close; `app.stop()` is unconditional.

Native applications should run on the Python main thread. The headless backend is for contracts, packaging and lifecycle tests; it does not prove desktop behavior. One process supports one active App at a time. Create a fresh App for each session.

On the main thread, `run()` temporarily bridges SIGINT using a 100 ms timer so Ctrl+C can stop a native wait. This uses one timer slot and up to ten timer wakeups per second. The previous signal handler is restored afterwards. Use `App(handle_sigint=False)` only when the host supplies its own interruption policy.

For local development only, `UI4ME_NATIVE_LIB` may name an absolute path to a native library. Installed consumers should not set it. No search of the current working directory, PATH or another checkout is performed. Unloading/replacing a library already loaded into the process is unsupported; restart Python after upgrading.

See the repository documentation for the release matrix, Python versions, native renderer limitations and publication setup.
