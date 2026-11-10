# Primary references

These references informed the foundation. They are external documentation, not
evidence that this reconstruction runs. Consult current upstream details when
updating dependencies or registry configuration.

| Topic | Primary source |
| --- | --- |
| winit event-loop model | https://docs.rs/winit/0.30.12/winit/event_loop/struct.EventLoop.html |
| Reusable native loop | https://docs.rs/winit/0.30.12/winit/platform/run_on_demand/trait.EventLoopExtRunOnDemand.html |
| Software presentation | https://docs.rs/softbuffer/0.4.6/softbuffer/ |
| Python callback ownership | https://docs.python.org/3/library/ctypes.html#callback-functions |
| Python platform wheel tags | https://packaging.python.org/en/latest/specifications/platform-compatibility-tags/ |
| auditwheel limitations | https://github.com/pypa/auditwheel |
| PyPI project creation via trusted publisher | https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/ |
| PyPI publisher configuration | https://docs.pypi.org/trusted-publishers/adding-a-publisher/ |
| PyPI publishing security model | https://docs.pypi.org/trusted-publishers/security-model/ |
| Publishing with GitHub Actions | https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/ |
| PowerShell Gallery account and API keys | https://learn.microsoft.com/en-us/powershell/gallery/how-to/getting-support/bootstrapping-nuget |
| Exact nupkg publication | https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.psresourceget/publish-psresource |
| PowerShell runspace thread policy | https://learn.microsoft.com/en-us/dotnet/api/system.management.automation.runspaces.psthreadoptions |
| .NET support policy | https://dotnet.microsoft.com/en-us/platform/support/policy |
| GitHub Pages organization hosting | https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages |
| Workflow security | https://docs.github.com/en/actions/reference/security/secure-use |
| Qt close lifecycle | https://doc.qt.io/qt-6/qwidget.html#close |
| GTK close request | https://docs.gtk.org/gtk4/signal.Window.close-request.html |
| Slint owner dispatch | https://docs.slint.dev/latest/docs/rust/slint/fn.invoke_from_event_loop.html |
| Electron lifecycle | https://www.electronjs.org/docs/latest/api/app |
| Tauri return-to-host | https://docs.rs/tauri/latest/tauri/struct.App.html |

The proposed MIT license covers this project's source. Third-party dependencies
retain their own terms. The first release must include the generated dependency
inventory and applicable license notices from its actual resolved graph.
