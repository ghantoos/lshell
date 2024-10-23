""" This module is used to run all the tests in the test directory. """

from test import test_functional, test_unit

if __name__ == "__main__":
    test_functional.unittest.main()
    test_unit.unittest.main()
