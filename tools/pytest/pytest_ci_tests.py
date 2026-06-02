from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
DISCOVERED_TEST_ROOTS = [
    "micropython",
    "python-ecosys",
    "python-stdlib",
]


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


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _discover_tests() -> list[str]:
    excluded_paths = {Path(path) for path in SCRIPT_TESTS}
    excluded_dirs = {REPO_ROOT / path for path in UNITTEST_PATHS}
    excluded_dirs.update(REPO_ROOT / path for path, _module in MODULE_TESTS)

    discovered_tests = []
    for root_name in DISCOVERED_TEST_ROOTS:
        root_path = REPO_ROOT / root_name
        for pattern in ("test_*.py", "test_*.mpy"):
            for test_path in sorted(root_path.rglob(pattern)):
                relative_path = test_path.relative_to(REPO_ROOT)
                if relative_path in excluded_paths:
                    continue
                if any(_is_relative_to(test_path, excluded_dir) for excluded_dir in excluded_dirs):
                    continue
                discovered_tests.append(relative_path.as_posix())

    return discovered_tests


DISCOVERED_TESTS = _discover_tests()



@pytest.mark.parametrize("test_path", SCRIPT_TESTS)
def test_micropython_script_tests(run_micropython, test_path):
    test_file = Path(test_path)
    run_micropython(test_file.name, cwd=REPO_ROOT / test_file.parent)


@pytest.mark.parametrize("test_path", UNITTEST_PATHS)
def test_micropython_unittest_packages(run_micropython, test_path):
    run_micropython("-m", "unittest", cwd=REPO_ROOT / test_path)


@pytest.mark.parametrize("test_path,module", MODULE_TESTS)
def test_micropython_module_tests(run_micropython, test_path, module):
    run_micropython("-m", module, cwd=REPO_ROOT / test_path)


@pytest.mark.parametrize("test_path", DISCOVERED_TESTS)
def test_micropython_discovered_tests(run_micropython, test_path):
    test_file = Path(test_path)
    run_micropython(test_file.name, cwd=REPO_ROOT / test_file.parent)
