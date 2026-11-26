import unittest

from CMD_Pal import calculate


class CalculatorTests(unittest.TestCase):
    def test_supports_basic_arithmetic_and_parentheses(self):
        self.assertEqual(calculate("12 * (4 + 3)"), 84)
        self.assertEqual(calculate("-5 + 2.5"), -2.5)
        self.assertEqual(calculate("2 ** 3"), 8)

    def test_rejects_code_and_unsupported_syntax(self):
        for expression in ("__import__('os').system('whoami')", "2 > 1", "x + 1"):
            with self.subTest(expression=expression):
                with self.assertRaises((ValueError, SyntaxError)):
                    calculate(expression)

    def test_rejects_division_by_zero_and_excessive_exponents(self):
        for expression in ("1 / 0", "2 ** 13"):
            with self.subTest(expression=expression):
                with self.assertRaises(ValueError):
                    calculate(expression)


if __name__ == "__main__":
    unittest.main()
