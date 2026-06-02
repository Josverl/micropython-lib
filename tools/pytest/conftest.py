import os
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MICROPYTHON_REPO = Path("/tmp/micropython")
DEFAULT_MICROPYTHON = DEFAULT_MICROPYTHON_REPO / "ports/unix/build-standard/micropython"

PACKAGE_TEST_LIBS = [
    ("micropython/ucontextlib/ucontextlib.py", False),
    ("python-stdlib/fnmatch/fnmatch.py", False),
    ("python-stdlib/hashlib-core/hashlib", True),
    ("python-stdlib/hashlib-sha224/hashlib", True),
    ("python-stdlib/hashlib-sha256/hashlib", True),
    ("python-stdlib/hashlib-sha384/hashlib", True),
    ("python-stdlib/hashlib-sha512/hashlib", True),
    ("python-stdlib/shutil/shutil.py", False),
    ("python-stdlib/tempfile/tempfile.py", False),
    ("python-stdlib/unittest/unittest", True),
    ("python-stdlib/unittest-discover/unittest", True),
    ("unix-ffi/ffilib/ffilib.py", False),
]


def _run_checked(*args, cwd=None):
    subprocess.run(args, cwd=cwd, check=True)


def _micropython_repo_path() -> Path:
    env_value = os.environ.get("MICROPYTHON_REPO")
    if env_value:
        return Path(env_value)
    return DEFAULT_MICROPYTHON_REPO


def _micropython_path() -> Path:
    env_value = os.environ.get("MICROPYTHON")
    if env_value:
        return Path(env_value)
    repo_path = _micropython_repo_path()
    return repo_path / "ports/unix/build-standard/micropython"


@pytest.fixture(scope="session")
def micropython_repo() -> Path:
    repo_path = _micropython_repo_path()
    branch = os.environ.get("MICROPYTHON_BRANCH", "master")

    if not (repo_path / ".git").exists():
        repo_path.parent.mkdir(parents=True, exist_ok=True)
        _run_checked(
            "git",
            "clone",
            "https://github.com/micropython/micropython.git",
            str(repo_path),
        )

    _run_checked("git", "-C", str(repo_path), "fetch", "origin", branch, "--depth=1")
    _run_checked("git", "-C", str(repo_path), "checkout", "-B", branch, "FETCH_HEAD")
    return repo_path


@pytest.fixture(scope="session")
def micropython_build(micropython_repo) -> Path:
    _run_checked("make", "-C", str(micropython_repo / "mpy-cross"), "-j", "CFLAGS_EXTRA=-O0")
    _run_checked("make", "-C", str(micropython_repo / "ports/unix"), "submodules")
    _run_checked("make", "-C", str(micropython_repo / "ports/unix"), "-j", "CFLAGS_EXTRA=-O0")
    return DEFAULT_MICROPYTHON


@pytest.fixture(scope="session")
def package_test_lib_setup() -> Path:
    target_dir = Path.home() / ".micropython/lib"
    target_dir.mkdir(parents=True, exist_ok=True)

    for relative_path, is_dir in PACKAGE_TEST_LIBS:
        source_path = REPO_ROOT / relative_path
        destination_path = target_dir / source_path.name
        if is_dir:
            shutil.copytree(source_path, destination_path, dirs_exist_ok=True)
        else:
            shutil.copy2(source_path, destination_path)

    return target_dir


@pytest.fixture(scope="session", autouse=True)
def package_test_environment(micropython_build, package_test_lib_setup):
    return micropython_build, package_test_lib_setup


@pytest.fixture(scope="session")
def micropython_executable(package_test_environment) -> str:
    path = _micropython_path()
    if not path.exists():
        pytest.skip(
            "MicroPython executable not found. "
            "Set MICROPYTHON or build at /tmp/micropython/ports/unix/build-standard/micropython."
        )
    return str(path)


@pytest.fixture(scope="session")
def run_micropython(micropython_executable):
    def _skip_reason(completed: subprocess.CompletedProcess[str]) -> str | None:
        for stream in (completed.stdout, completed.stderr):
            for line in stream.splitlines():
                normalized = line.strip().lower()
                if normalized == "skip" or normalized.startswith("skip:"):
                    return line.strip()
        return None

    def _run(*args, cwd: Path):
        completed = subprocess.run(
            [micropython_executable, *args],
            cwd=str(cwd),
            text=True,
            capture_output=True,
            check=False,
        )
        skip_reason = _skip_reason(completed)
        if skip_reason is not None:
            pytest.skip(skip_reason)
        if completed.returncode != 0:
            pytest.fail(
                "MicroPython command failed\n"
                + f"cwd: {cwd}\n"
                + f"command: {micropython_executable} {' '.join(args)}\n"
                + f"stdout:\n{completed.stdout}\n"
                + f"stderr:\n{completed.stderr}"
            )

    return _run
