import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--per-test-case",
        action="store_true",
        default=False,
        help=(
            "Run each MicroPython unittest case individually via the unittest adapter "
            "(granular pass/fail/skip per method, but slower due to one MicroPython "
            "invocation per case). Default: run each unittest path once with -m unittest "
            "to mirror tools/ci.sh."
        ),
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "micropython_unittest_path(unittest_path, case_targets): "
        "internal marker carrying per-path unittest metadata for pytest_generate_tests",
    )


def pytest_generate_tests(metafunc):
    if "unittest_target" not in metafunc.fixturenames:
        return
    marker = metafunc.definition.get_closest_marker("micropython_unittest_path")
    if not marker:
        return
    unittest_path = marker.kwargs["unittest_path"]
    case_targets = marker.kwargs["case_targets"]
    if metafunc.config.getoption("--per-test-case"):
        metafunc.parametrize("unittest_target", case_targets, ids=case_targets)
    else:
        metafunc.parametrize("unittest_target", [None], ids=[unittest_path])


REPO_ROOT = Path(__file__).resolve().parent
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


def _sanitize_name(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z_]+", "_", text).strip("_")


def _extract_path_level_unittest_nodeid(nodeid: str) -> str | None:
    # Path-level node ids look like:
    # tools/pytest/pytest_ci_tests.py::test_unittest_xxx[python-stdlib/datetime]
    # Per-case node ids include "::" inside the brackets and are ignored here.
    match = re.search(r"::test_unittest_[^\[]+\[([^\]]+)\]$", nodeid)
    if not match:
        return None
    unittest_path = match.group(1)
    if "::" in unittest_path:
        return None
    return unittest_path


def _split_failure_sections(stdout: str) -> list[str]:
    sections = []
    starts = [m.start() for m in re.finditer(r"^FAIL:\s+", stdout, re.MULTILINE)]
    if not starts:
        return sections
    starts.append(len(stdout))
    for index in range(len(starts) - 1):
        sections.append(stdout[starts[index] : starts[index + 1]])
    return sections


def _failure_case_from_section(section: str) -> tuple[str | None, str | None]:
    fail_match = re.search(r"^FAIL:\s+(test\S+)\s+<(class|function)\s+'([^']+)'", section, re.MULTILINE)
    if not fail_match:
        return None, None

    test_name = fail_match.group(1)
    kind = fail_match.group(2)
    owner_name = fail_match.group(3)

    file_match = re.search(r'File "(?:\./)?([^"/]+\.py)"', section)
    filename = file_match.group(1) if file_match else None

    if kind == "class":
        case_id = f"{owner_name}.{test_name}"
    else:
        case_id = test_name

    return filename, case_id


def _single_test_filename(unittest_path: str) -> str | None:
    root = REPO_ROOT / unittest_path
    files = sorted(path.name for path in root.rglob("test*.py"))
    if len(files) == 1:
        return files[0]
    return None


def _build_per_case_rerun_hints(stdout: str) -> list[str]:
    current_test = os.environ.get("PYTEST_CURRENT_TEST", "").split(" ", 1)[0]
    unittest_path = _extract_path_level_unittest_nodeid(current_test)
    if not unittest_path:
        return []

    test_function_name = f"test_unittest_{_sanitize_name(unittest_path)}"
    fallback_filename = _single_test_filename(unittest_path)
    k_commands = []

    for section in _split_failure_sections(stdout):
        filename, case_id = _failure_case_from_section(section)
        if not case_id:
            continue
        chosen_filename = filename or fallback_filename
        if not chosen_filename:
            continue

        k_expr = f"{test_function_name} and {chosen_filename} and {case_id}"
        k_commands.append(
            "uv run pytest --per-test-case -q tools/pytest/pytest_ci_tests.py "
            + f'-k "{k_expr}"'
        )

    # Keep order stable while removing duplicates.
    deduped_k_commands = list(dict.fromkeys(k_commands))
    return deduped_k_commands


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
def run_micropython_raw(micropython_executable):
    def _run(*args, cwd: Path):
        return subprocess.run(
            [micropython_executable, *args],
            cwd=str(cwd),
            text=True,
            capture_output=True,
            check=False,
        )

    return _run


@pytest.fixture(scope="session")
def run_micropython(run_micropython_raw, micropython_executable):
    def _skip_reason(completed: subprocess.CompletedProcess[str]) -> str | None:
        for stream in (completed.stdout, completed.stderr):
            for line in stream.splitlines():
                normalized = line.strip().lower()
                if normalized == "skip" or normalized.startswith("skip:"):
                    return line.strip()
        return None

    def _run(*args, cwd: Path):
        completed = run_micropython_raw(*args, cwd=cwd)
        skip_reason = _skip_reason(completed)
        if skip_reason is not None:
            pytest.skip(skip_reason)
        if completed.returncode != 0:
            rerun_k_hints = _build_per_case_rerun_hints(completed.stdout)
            hints_block = ""
            if rerun_k_hints:
                hints_block = (
                    "\nPer-case rerun commands (-k):\n"
                    + "\n".join(rerun_k_hints)
                    + "\n"
                )
            pytest.fail(
                "MicroPython command failed\n"
                + f"cwd: {cwd}\n"
                + f"command: {micropython_executable} {' '.join(args)}\n"
                + f"stdout:\n{completed.stdout}\n"
                + f"stderr:\n{completed.stderr}"
                + hints_block
            )

    return _run
