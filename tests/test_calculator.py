import hashlib
from io import BytesIO
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from CMD_Pal import (
    ACCENT_PRESETS,
    blend_colors,
    build_startup_command,
    calculate,
    download_verified_update,
    is_hex_color,
    parse_release_update,
    parse_release_version,
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


class UpdateVersionTests(unittest.TestCase):
    def test_parses_release_versions_for_update_comparison(self):
        self.assertEqual(parse_release_version("v1.12.3"), (1, 12, 3))
        self.assertEqual(parse_release_version("1.2.0"), (1, 2, 0))

    def test_rejects_unexpected_release_tags(self):
        for tag in ("latest", "v1.2", "../v2.0.0"):
            with self.subTest(tag=tag):
                with self.assertRaises(ValueError):
                    parse_release_version(tag)

    def test_detects_new_release_and_validates_download_metadata(self):
        digest = "a" * 64
        update = parse_release_update({
            "tag_name": "v1.4.0",
            "assets": [{
                "name": "CMD-Pal.exe",
                "browser_download_url": "https://github.com/marlohowe/cmd-pal/releases/download/v1.4.0/CMD-Pal.exe",
                "digest": "sha256:" + digest,
            }],
        })
        self.assertEqual(update["tag"], "v1.4.0")
        self.assertEqual(update["digest"], digest)

    def test_reports_no_update_and_rejects_untrusted_downloads(self):
        self.assertIsNone(parse_release_update({"tag_name": "v1.2.0", "assets": []}))
        unsafe_release = {
            "tag_name": "v1.4.0",
            "assets": [{
                "name": "CMD-Pal.exe",
                "browser_download_url": "https://example.com/CMD-Pal.exe",
                "digest": "sha256:" + "a" * 64,
            }],
        }
        with self.assertRaises(ValueError):
            parse_release_update(unsafe_release)


class UpdateDownloadTests(unittest.TestCase):
    def test_downloads_only_a_checksum_verified_windows_executable(self):
        executable = b"MZtest executable"
        update = {
            "tag": "v1.4.0",
            "url": "https://github.com/marlohowe/cmd-pal/releases/download/v1.4.0/CMD-Pal.exe",
            "digest": hashlib.sha256(executable).hexdigest(),
        }
        with tempfile.TemporaryDirectory() as directory:
            with patch("CMD_Pal.urllib.request.urlopen", return_value=BytesIO(executable)):
                downloaded = download_verified_update(update, directory)
            self.assertEqual(downloaded.read_bytes(), executable)
            self.assertEqual(downloaded.name, "CMD-Pal.exe")

    def test_rejects_bad_checksum_without_leaving_a_download(self):
        update = {
            "tag": "v1.4.0",
            "url": "https://github.com/marlohowe/cmd-pal/releases/download/v1.4.0/CMD-Pal.exe",
            "digest": "0" * 64,
        }
        with tempfile.TemporaryDirectory() as directory:
            with patch("CMD_Pal.urllib.request.urlopen", return_value=BytesIO(b"MZwrong")):
                with self.assertRaisesRegex(ValueError, "checksum"):
                    download_verified_update(update, directory)
            self.assertEqual(list(Path(directory).rglob("*")), [Path(directory) / "v1.4.0"])
            self.assertFalse((Path(directory) / "v1.4.0" / "CMD-Pal.exe").exists())


if __name__ == "__main__":
    unittest.main()
