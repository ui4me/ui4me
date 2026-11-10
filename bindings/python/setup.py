"""Native payloads are staged by dev.py; the wrapper itself is Python ABI independent."""
from setuptools import Distribution, setup
from wheel.bdist_wheel import bdist_wheel
from pathlib import Path
import platform


class NativeDistribution(Distribution):
    def has_ext_modules(self):
        return True


class PlatformWheel(bdist_wheel):
    def run(self):
        names = {"Windows": "ui4me_core.dll", "Linux": "libui4me_core.so"}
        name = names.get(platform.system())
        payload = Path(__file__).parent / "src" / "ui4me" / "_native"
        if not name or not (payload / name).is_file():
            raise RuntimeError("The matching native runtime must be staged before building a wheel")
        super().run()

    def finalize_options(self):
        super().finalize_options()
        self.root_is_pure = False

    def get_tag(self):
        _, _, platform_tag = super().get_tag()
        return "py3", "none", platform_tag


setup(distclass=NativeDistribution, cmdclass={"bdist_wheel": PlatformWheel})
