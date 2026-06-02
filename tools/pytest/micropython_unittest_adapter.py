"""Run a single unittest case inside MicroPython for pytest integration.

This adapter is executed by the host-side pytest wrapper. It imports one test
module and runs exactly one selected test function or test method, then exits
with a status code that pytest can map to pass/fail/skip.
"""

import sys

import unittest


def _strip_ext(filename):
    """Return a module-like name by removing .py or .mpy extension."""
    if filename.endswith(".py") or filename.endswith(".mpy"):
        return filename.rsplit(".", 1)[0]
    return filename


def _dirname_and_modname(path):
    """Split a file path into import directory and module name without extension."""
    path = path.replace("\\", "/")
    split = path.rsplit("/", 1)
    if len(split) == 1:
        return "", _strip_ext(split[0])
    return split[0], _strip_ext(split[1])


def _parse_args(argv):
    """Parse adapter CLI args and return (test_file, test_case)."""
    test_file = None
    test_case = None

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--file" and i + 1 < len(argv):
            test_file = argv[i + 1]
            i += 2
            continue
        if arg == "--case" and i + 1 < len(argv):
            test_case = argv[i + 1]
            i += 2
            continue
        raise ValueError("Unexpected argument: %s" % arg)

    if not test_file or not test_case:
        raise ValueError("Usage: micropython_unittest_adapter.py --file <path> --case <case-id>")

    return test_file, test_case


def _single_method_class(cls, method_name):
    """Create a temporary class variant that exposes only one test method."""
    attrs = {}
    for name in dir(cls):
        if name.startswith("test") and name != method_name:
            attrs[name] = None
    return type("_SingleCase", (cls,), attrs)


def _build_suite(module, case_id):
    """Build a unittest suite for one test function or ClassName.test_method."""
    suite = unittest.TestSuite(module.__name__)

    if "." in case_id:
        class_name, method_name = case_id.rsplit(".", 1)
        cls = getattr(module, class_name)
        suite.addTest(_single_method_class(cls, method_name))
    else:
        suite.addTest(getattr(module, case_id))

    return suite


def main():
    """Adapter entrypoint used by the pytest harness."""
    test_file, test_case = _parse_args(sys.argv[1:])

    dirname, module_name = _dirname_and_modname(test_file)
    if dirname:
        sys.path.insert(0, dirname)

    module = __import__(module_name)
    suite = _build_suite(module, test_case)
    result = unittest.TestRunner().run(suite)

    # Keep a machine-readable summary for debugging host-side failures.
    print(
        "__MPYTEST_RESULT__ run=%d failures=%d errors=%d skipped=%d"
        % (result.testsRun, result.failuresNum, result.errorsNum, result.skippedNum)
    )

    if result.failuresNum or result.errorsNum or result.unexpectedSuccessesNum:
        sys.exit(1)
    if result.testsRun and result.testsRun == result.skippedNum:
        sys.exit(5)
    sys.exit(0)


main()
