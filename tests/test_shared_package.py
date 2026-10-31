"""Smoke tests for the shared package scaffold; standard-library only."""

import unittest

import shared


class SharedPackageTests(unittest.TestCase):
    def test_shared_package_imports(self) -> None:
        self.assertTrue(shared.__doc__)


if __name__ == "__main__":
    unittest.main()
