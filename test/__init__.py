""" This module is used to run all the tests in the test directory. """

from test import test_functional_p1, test_unit, test_functional_p2

if __name__ == "__main__":
    test_functional_p1.unittest.main()
    test_functional_p2.unittest.main()
    test_unit.unittest.main()
