import ast
import re
import warnings
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]  # tools/pytest/ -> repo root
UNITTEST_ADAPTER = Path("tools/pytest/micropython_unittest_adapter.py")


SCRIPT_TESTS = [
    "micropython/drivers/storage/sdcard/sdtest.py",
    "micropython/xmltok/test_xmltok.py",
    "python-ecosys/requests/test_requests.py",
    "python-stdlib/argparse/test_argparse.py",
    "python-stdlib/base64/test_base64.py",
    "python-stdlib/binascii/test_binascii.py",
    "python-stdlib/collections-defaultdict/test_defaultdict.py",
    "python-stdlib/functools/test_partial.py",
    "python-stdlib/functools/test_reduce.py",
    "python-stdlib/heapq/test_heapq.py",
    "python-stdlib/hmac/test_hmac.py",
    "python-stdlib/itertools/test_itertools.py",
    "python-stdlib/operator/test_operator.py",
    "python-stdlib/os-path/test_path.py",
    "python-stdlib/pickle/test_pickle.py",
    "python-stdlib/string/test_translate.py",
    "python-stdlib/unittest/tests/exception.py",
    "unix-ffi/gettext/test_gettext.py",
    "unix-ffi/pwd/test_getpwnam.py",
    "unix-ffi/re/test_re.py",
    "unix-ffi/sqlite3/test_sqlite3.py",
    "unix-ffi/sqlite3/test_sqlite3_2.py",
    "unix-ffi/sqlite3/test_sqlite3_3.py",
    "unix-ffi/time/test_strftime.py",
]


UNITTEST_PATHS = [
    "micropython/ucontextlib",
    "python-stdlib/contextlib",
    "python-stdlib/datetime",
    "python-stdlib/fnmatch",
    "python-stdlib/hashlib",
    "python-stdlib/inspect",
    "python-stdlib/pathlib",
    "python-stdlib/quopri",
    "python-stdlib/shutil",
    "python-stdlib/tarfile",
    "python-stdlib/tempfile",
    "python-stdlib/time",
    "python-stdlib/unittest/tests",
    "python-stdlib/unittest-discover/tests",
]


MODULE_TESTS = [
    ("micropython/usb/usb-device", "tests.test_core_buffer"),
    ("python-ecosys/cbor2", "examples.cbor_test"),
]


def _discover_unittest_files_by_path() -> dict[str, list[str]]:
    unittest_files_by_path = {}
    for unittest_path in UNITTEST_PATHS:
        root_path = REPO_ROOT / unittest_path
        files = [
            module_path.relative_to(REPO_ROOT).as_posix()
            for module_path in sorted(root_path.rglob("test*.py"))
        ]
        if files:
            unittest_files_by_path[unittest_path] = files
    return unittest_files_by_path


def _discover_unittest_case_targets_by_path() -> dict[str, list[str]]:
    unittest_case_targets_by_path = {}
    for unittest_path, test_files in UNITTEST_FILES_BY_PATH.items():
        targets = []
        for test_path in test_files:
            file_path = REPO_ROOT / test_path
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)
                tree = ast.parse(file_path.read_text())

            cases = []
            for node in tree.body:
                if isinstance(node, ast.FunctionDef) and node.name.startswith("test"):
                    cases.append(node.name)
                if isinstance(node, ast.ClassDef):
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef) and item.name.startswith("test"):
                            cases.append(f"{node.name}.{item.name}")

            for case in cases:
                targets.append(f"{test_path}::{case}")

        if targets:
            unittest_case_targets_by_path[unittest_path] = targets

    return unittest_case_targets_by_path


def _sanitize_name(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z_]+", "_", text).strip("_")


def _first_skip_line(*streams: str) -> str | None:
    for stream in streams:
        for line in stream.splitlines():
            if " skipped:" in line:
                return line.strip()
    return None


UNITTEST_FILES_BY_PATH = _discover_unittest_files_by_path()
UNITTEST_CASE_TARGETS_BY_PATH = _discover_unittest_case_targets_by_path()


def _split_case_target(case_target: str) -> tuple[str, str]:
    test_path, test_case = case_target.split("::", 1)
    return test_path, test_case


def _run_unittest_case(run_micropython_raw, test_path, test_case):
    completed = run_micropython_raw(
        str(UNITTEST_ADAPTER),
        "--file",
        test_path,
        "--case",
        test_case,
        cwd=REPO_ROOT,
    )

    if completed.returncode == 5:
        skip_line = _first_skip_line(completed.stdout, completed.stderr)
        pytest.skip(skip_line or "MicroPython unittest case skipped")

    if completed.returncode != 0:
        pytest.fail(
            "MicroPython unittest case failed\n"
            + f"case: {test_path}::{test_case}\n"
            + f"stdout:\n{completed.stdout}\n"
            + f"stderr:\n{completed.stderr}"
        )


def _register_unittest_path_tests():
    for unittest_path, case_targets in UNITTEST_CASE_TARGETS_BY_PATH.items():
        test_name = f"test_unittest_{_sanitize_name(unittest_path)}"

        @pytest.mark.micropython_unittest_path(
            unittest_path=unittest_path,
            case_targets=case_targets,
        )
        def _test(run_micropython_raw, run_micropython, unittest_target, _unittest_path=unittest_path):
            if unittest_target is None:
                # default mode mirrors tools/ci.sh: run unittest once per path.
                run_micropython("-m", "unittest", cwd=REPO_ROOT / _unittest_path)
            else:
                # per-test-case mode: one adapter invocation per case.
                test_path, test_case = _split_case_target(unittest_target)
                _run_unittest_case(run_micropython_raw, test_path, test_case)

        _test.__name__ = test_name
        _test.__doc__ = unittest_path
        globals()[test_name] = _test



@pytest.mark.parametrize("test_path", SCRIPT_TESTS)
def test_micropython_script_tests(run_micropython, test_path):
    test_file = Path(test_path)
    run_micropython(test_file.name, cwd=REPO_ROOT / test_file.parent)


_register_unittest_path_tests()


@pytest.mark.parametrize("test_path,module", MODULE_TESTS)
def test_micropython_module_tests(run_micropython, test_path, module):
    run_micropython("-m", module, cwd=REPO_ROOT / test_path)
