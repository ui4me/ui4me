"""Executed only by an explicitly requested local test run."""
import json
import sys
import unittest
from pathlib import Path


class Results(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cases = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.cases.append({"id": test.id(), "status": "passed"})

    def addFailure(self, test, error):
        super().addFailure(test, error)
        self.cases.append({"id": test.id(), "status": "failed", "details": self._exc_info_to_string(error, test)})

    def addError(self, test, error):
        super().addError(test, error)
        self.cases.append({"id": test.id(), "status": "failed", "details": self._exc_info_to_string(error, test)})

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.cases.append({"id": test.id(), "status": "blocked", "details": reason})

    def addExpectedFailure(self, test, error):
        super().addExpectedFailure(test, error)
        self.cases.append({"id": test.id(), "status": "blocked", "details": "Expected failure does not count as release coverage"})

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self.cases.append({"id": test.id(), "status": "failed", "details": "Unexpected success; update test expectation"})


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.discover(sys.argv[1])
    result = unittest.TextTestRunner(verbosity=2, resultclass=Results).run(suite)
    Path(sys.argv[2]).write_text(json.dumps({"tests": result.testsRun, "cases": result.cases}, indent=2), encoding="utf-8")
    raise SystemExit(0 if result.testsRun > 0 and result.wasSuccessful() and not result.skipped and not result.expectedFailures else 1)
