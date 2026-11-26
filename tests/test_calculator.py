import tempfile
import unittest
from pathlib import Path

from CMD_Pal import (
    ACCENT_PRESETS,
    blend_colors,
    build_startup_command,
    calculate,
    is_hex_color,
    result_icon_type,
)


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


class AppearanceTests(unittest.TestCase):
    def test_file_icons_follow_file_type(self):
        self.assertEqual(result_icon_type("photo.png", "photo.png", "file"), "image")
        self.assertEqual(result_icon_type("notes.txt", "notes.txt", "file"), "document")
        self.assertEqual(result_icon_type("main.py", "main.py", "file"), "code")

    def test_app_and_custom_shortcut_icons(self):
        self.assertEqual(result_icon_type("Firefox", "firefox.exe", "app"), "browser")
        website = [{"name": "Docs", "type": "website"}]
        self.assertEqual(
            result_icon_type("Docs", "cmdpal:website:Docs", "command", website),
            "website",
        )

    def test_accent_presets_and_color_validation(self):
        self.assertEqual(blend_colors("#ffffff", ACCENT_PRESETS["Blue"], 0), "#ffffff")
        self.assertTrue(is_hex_color("#a1B2c3"))
        self.assertFalse(is_hex_color("blue"))
        self.assertFalse(is_hex_color("#12345g"))


if __name__ == "__main__":
    unittest.main()
