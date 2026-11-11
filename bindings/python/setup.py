"""Build platform wheels from a staged library or the bundled source archive."""
import hashlib
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

from setuptools import Distribution, setup
from setuptools.command.sdist import sdist
from wheel.bdist_wheel import bdist_wheel


HERE = Path(__file__).resolve().parent
NATIVE_SOURCE = HERE / "native-source"
# PEP 517 executes setup.py without guaranteeing its directory on sys.path.
_support_spec = importlib.util.spec_from_file_location("ui4me_source_support", HERE / "_build_support.py")
_support = importlib.util.module_from_spec(_support_spec)
_support_spec.loader.exec_module(_support)
stage_native_source, collect_notices = _support.stage_native_source, _support.collect_notices


class SourceDistribution(sdist):
    """Include the locked native workspace so an sdist builds independently."""

    def make_release_tree(self, base_dir, files):
        # A prior wheel build may have staged a platform payload and notices
        # under src. They are outputs, not inputs to a portable source archive.
        files = [name for name in files
                 if not name.replace("\\", "/").startswith(("src/ui4me/_native/", "src/ui4me/_notices/"))]
        super().make_release_tree(base_dir, files)
        # A checkout has the workspace two directories above this package;
        # a repacked sdist has its own private source workspace.
        checkout = HERE.parents[1]
        source = NATIVE_SOURCE if NATIVE_SOURCE.is_dir() else checkout
        if not (source / "Cargo.lock").is_file() or not (source / "crates/ui4me-core/Cargo.toml").is_file():
            raise RuntimeError("The locked ui4me native workspace is required to build an sdist")
        target = Path(base_dir) / "native-source"
        stage_native_source(source, target)
        shutil.copy2(HERE / "_build_support.py", Path(base_dir) / "_build_support.py")
        license_file = HERE / "LICENSE" if (HERE / "LICENSE").is_file() else checkout / "LICENSE"
        if not license_file.is_file():
            raise RuntimeError("The project license is required to build an sdist")
        shutil.copy2(license_file, Path(base_dir) / "LICENSE")
        # setuptools may have cached staged package-data paths in SOURCES.txt.
        # Keep the archive's own file inventory accurate when repacking.
        for manifest in Path(base_dir).glob("src/*.egg-info/SOURCES.txt"):
            lines = [line for line in manifest.read_text(encoding="utf-8").splitlines()
                     if not line.replace("\\", "/").startswith(("src/ui4me/_native/", "src/ui4me/_notices/"))]
            lines += [path.relative_to(base_dir).as_posix() for path in target.rglob("*") if path.is_file()]
            lines.append("LICENSE")
            lines.append("_build_support.py")
            manifest.write_text("\n".join(sorted(set(lines))) + "\n", encoding="utf-8")


def build_native_from_sdist(name):
    """An sdist has no prebuilt payload: build its own locked native core."""
    if not (NATIVE_SOURCE / "Cargo.lock").is_file():
        raise RuntimeError("The matching native runtime must be staged before building a wheel")
    digest = hashlib.sha256()
    paths = [HERE / "setup.py", HERE / "pyproject.toml", HERE / "_build_support.py"]
    paths += [p for root in (HERE / "src/ui4me", NATIVE_SOURCE) for p in root.rglob("*")
              if p.is_file() and not any(part in {"_native", "_notices", "__pycache__", "target"} for part in p.parts)]
    for path in sorted(paths, key=lambda item: item.relative_to(HERE).as_posix().encode("utf-8")):
        relative = path.relative_to(HERE).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big")); digest.update(relative)
        digest.update(len(content).to_bytes(8, "big")); digest.update(content)
    env = dict(os.environ, UI4ME_SOURCE_ID="sdist-sha256:" + digest.hexdigest(), UI4ME_GIT_REVISION="sdist")
    native_target = {"Windows": "x86_64-pc-windows-msvc", "Linux": "x86_64-unknown-linux-gnu"}[platform.system()]
    env.pop("CARGO_BUILD_TARGET", None)
    with tempfile.TemporaryDirectory(prefix="ui4me-native-build-") as target:
        env["CARGO_TARGET_DIR"] = target
        try:
            subprocess.run(["cargo", "build", "--locked", "--release", "--target", native_target, "-p", "ui4me-core"], cwd=NATIVE_SOURCE, env=env, check=True)
        except FileNotFoundError as error:
            raise RuntimeError("Building ui4me from source requires the Rust toolchain; install a platform wheel instead") from error
        payload = HERE / "src/ui4me/_native"
        payload.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(target) / native_target / "release" / name, payload / name)
        # Keep the dependency inventory and license texts in source-built
        # wheels too, just as dev.py does for its staged platform wheels.
        metadata = subprocess.run(["cargo", "metadata", "--locked", "--format-version", "1"],
                                  cwd=NATIVE_SOURCE, env=env, check=True, capture_output=True, text=True)
        notices = HERE / "src/ui4me/_notices"
        collect_notices(json.loads(metadata.stdout), notices)
        if (HERE / "LICENSE").is_file():
            shutil.copy2(HERE / "LICENSE", notices / "LICENSE")


class NativeDistribution(Distribution):
    def has_ext_modules(self):
        return True


class PlatformWheel(bdist_wheel):
    def run(self):
        names = {"Windows": "ui4me_core.dll", "Linux": "libui4me_core.so"}
        name = names.get(platform.system())
        payload = HERE / "src" / "ui4me" / "_native"
        if not name:
            raise RuntimeError("Building ui4me wheels is supported on Linux and Windows")
        if not (payload / name).is_file():
            build_native_from_sdist(name)
        super().run()

    def finalize_options(self):
        super().finalize_options()
        self.root_is_pure = False

    def get_tag(self):
        _, _, platform_tag = super().get_tag()
        return "py3", "none", platform_tag


setup(distclass=NativeDistribution, cmdclass={"bdist_wheel": PlatformWheel, "sdist": SourceDistribution})
