import argparse
import base64
import importlib.util
import io
import json
import os
import struct
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "scripts" / "generate_image.py"
SPEC = importlib.util.spec_from_file_location("generate_image", SCRIPT)
generate_image = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generate_image)


def png_bytes(width=2, height=3):
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + struct.pack(">II", width, height) + b"\x00" * 16


def jpeg_bytes(width=4, height=5):
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
    sof0 = b"\xff\xc0" + struct.pack(">H", 17) + b"\x08" + struct.pack(">HH", height, width) + b"\x03" + b"\x00" * 9
    return b"\xff\xd8" + app0 + sof0 + b"\xff\xd9"


def webp_vp8_bytes(width=6, height=7):
    payload = b"\x00" * 3 + b"\x9d\x01\x2a" + struct.pack("<HH", width, height)
    return b"RIFF" + struct.pack("<I", 4 + 8 + len(payload)) + b"WEBP" + b"VP8 " + struct.pack("<I", len(payload)) + payload


def webp_vp8l_bytes(width=8, height=9):
    bits = (width - 1) | ((height - 1) << 14)
    payload = b"\x2f" + bits.to_bytes(4, "little")
    return b"RIFF" + struct.pack("<I", 4 + 8 + len(payload)) + b"WEBP" + b"VP8L" + struct.pack("<I", len(payload)) + payload


def webp_vp8x_bytes(width=10, height=11):
    payload = b"\x00" * 4 + (width - 1).to_bytes(3, "little") + (height - 1).to_bytes(3, "little")
    return b"RIFF" + struct.pack("<I", 4 + 8 + len(payload)) + b"WEBP" + b"VP8X" + struct.pack("<I", len(payload)) + payload


def make_args(**overrides):
    defaults = {
        "prompt": "a cat",
        "prompt_file": None,
        "model": "gpt-image-1",
        "size": "1024x1024",
        "quality": None,
        "response_format": None,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


class GenerateImageTest(unittest.TestCase):
    def test_load_config_requires_both_environment_variables(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, r"^OPENAI_BASE_URL and OPENAI_API_KEY not set"):
                generate_image.load_config()

    def test_load_config_names_only_the_missing_variable(self):
        env = {"OPENAI_BASE_URL": "https://example.test/v1"}
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(ValueError, r"^OPENAI_API_KEY not set"):
                generate_image.load_config()

    def test_load_config_error_includes_setup_instructions(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "export OPENAI_API_KEY"):
                generate_image.load_config()

    def test_endpoint_normalizes_versioned_base_url(self):
        self.assertEqual(
            "https://example.test/v1/images/generations",
            generate_image.generation_endpoint("https://example.test/v1/"),
        )

    def test_payload_omits_optional_parameters_by_default(self):
        payload = generate_image.build_payload("a cat", make_args())
        self.assertEqual({"model": "gpt-image-1", "prompt": "a cat", "n": 1, "size": "1024x1024"}, payload)

    def test_payload_includes_optional_parameters_when_set(self):
        payload = generate_image.build_payload("a cat", make_args(quality="high", response_format="b64_json"))
        self.assertEqual("high", payload["quality"])
        self.assertEqual("b64_json", payload["response_format"])

    def test_resolve_prompt_reads_prompt_file(self):
        with tempfile.TemporaryDirectory() as directory:
            prompt_file = Path(directory) / "prompt.txt"
            prompt_file.write_text('a "quoted" $prompt\n', encoding="utf-8")
            prompt = generate_image.resolve_prompt(make_args(prompt=None, prompt_file=prompt_file))
        self.assertEqual('a "quoted" $prompt', prompt)

    def test_resolve_prompt_rejects_empty_prompt(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            generate_image.resolve_prompt(make_args(prompt="   "))

    def test_extracts_base64_image(self):
        encoded = base64.b64encode(png_bytes()).decode("ascii")
        self.assertEqual(png_bytes(), generate_image.extract_image_bytes({"data": [{"b64_json": encoded}]}))

    def test_rejects_invalid_base64(self):
        with self.assertRaisesRegex(ValueError, "invalid base64"):
            generate_image.extract_image_bytes({"data": [{"b64_json": "not!!valid=="}]})

    def test_downloads_url_image(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = png_bytes()
        with mock.patch.object(generate_image.urllib.request, "urlopen", return_value=response):
            result = generate_image.extract_image_bytes({"data": [{"url": "https://example.test/image.png"}]})
        self.assertEqual(png_bytes(), result)

    def test_heartbeat_emits_progress_until_stopped(self):
        stderr = io.StringIO()
        with mock.patch.object(generate_image.sys, "stderr", stderr):
            stop = generate_image.start_heartbeat("the test", interval=0.01)
            deadline = time.monotonic() + 2
            while "still waiting" not in stderr.getvalue() and time.monotonic() < deadline:
                time.sleep(0.01)
            stop.set()
        self.assertIn("still waiting for the test", stderr.getvalue())

    def test_timeout_flag_defaults_to_600_and_is_overridable(self):
        with mock.patch.object(sys, "argv", ["prog", "--prompt", "x", "--output", "o.png"]):
            self.assertEqual(600, generate_image.parse_args().timeout)
        with mock.patch.object(sys, "argv", ["prog", "--prompt", "x", "--output", "o.png", "--timeout", "60"]):
            self.assertEqual(60, generate_image.parse_args().timeout)

    def test_api_request_uses_given_timeout(self):
        response = mock.MagicMock()
        response.__enter__.return_value = io.StringIO('{"data": []}')
        with mock.patch.object(generate_image.urllib.request, "urlopen", return_value=response) as urlopen:
            generate_image.api_request("https://example.test/v1", "key", {"prompt": "x"}, timeout=123)
        self.assertEqual(123, urlopen.call_args.kwargs["timeout"])

    def test_redacts_api_key_from_http_error(self):
        secret = "secret-token-value"
        error = generate_image.ApiError(403, json.dumps({"error": secret}), secret)
        self.assertNotIn(secret, str(error))
        self.assertIn("[REDACTED]", str(error))

    def test_parses_png_dimensions(self):
        self.assertEqual(("PNG", 2, 3), generate_image.image_info(png_bytes(2, 3)))

    def test_parses_jpeg_dimensions(self):
        self.assertEqual(("JPEG", 4, 5), generate_image.image_info(jpeg_bytes(4, 5)))

    def test_parses_webp_vp8_dimensions(self):
        self.assertEqual(("WebP", 6, 7), generate_image.image_info(webp_vp8_bytes(6, 7)))

    def test_parses_webp_vp8l_dimensions(self):
        self.assertEqual(("WebP", 8, 9), generate_image.image_info(webp_vp8l_bytes(8, 9)))

    def test_parses_webp_vp8x_dimensions(self):
        self.assertEqual(("WebP", 10, 11), generate_image.image_info(webp_vp8x_bytes(10, 11)))

    def test_writes_validated_image_and_reports_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "nested" / "image.png"
            metadata = generate_image.write_validated_image(png_bytes(2, 3), output)
            self.assertEqual((2, 3), (metadata["width"], metadata["height"]))
            self.assertEqual("PNG", metadata["format"])
            self.assertTrue(output.exists())

    def test_rejects_non_image_response(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "recognized PNG, JPEG, or WebP"):
                generate_image.write_validated_image(b'{"error":"not an image"}', Path(directory) / "bad.png")

    def test_rejects_truncated_jpeg_without_frame_header(self):
        with self.assertRaises(ValueError):
            generate_image.image_info(b"\xff\xd8\xff\xd9")


if __name__ == "__main__":
    unittest.main()
