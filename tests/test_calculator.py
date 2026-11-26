import tempfile
import unittest
from pathlib import Path

from CMD_Pal import build_startup_command, calculate


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


class StartupCommandTests(unittest.TestCase):
    def test_frozen_app_registers_itself_with_startup_flag(self):
        command = build_startup_command(
            r"C:\Apps\CMD Pal.exe", "CMD_Pal.py", frozen=True
        )
        self.assertIn("--startup", command)
        self.assertIn("CMD Pal.exe", command)

    def test_python_source_uses_pythonw_and_startup_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            pythonw = Path(directory) / "pythonw.exe"
            source = Path(directory) / "CMD Pal.py"
            pythonw.touch()
            source.touch()
            command = build_startup_command("python.exe", source, False, pythonw)
            self.assertIn("pythonw.exe", command)
            self.assertIn(str(source.resolve()), command)
            self.assertIn("--startup", command)

    def test_source_startup_requires_pythonw(self):
        with self.assertRaises(OSError):
            build_startup_command("python.exe", "CMD_Pal.py", False)


if __name__ == "__main__":
    unittest.main()
