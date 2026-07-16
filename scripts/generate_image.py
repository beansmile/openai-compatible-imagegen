#!/usr/bin/env python3
import argparse
import base64
import hashlib
import json
import os
import struct
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path


USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/138.0 Safari/537.36"

# SOF0-SOF15 minus the non-frame markers DHT (C4), JPG (C8), DAC (CC).
JPEG_SOF_MARKERS = frozenset(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}


def redact(text, api_key):
    return text.replace(api_key, "[REDACTED]") if api_key else text


class ApiError(RuntimeError):
    def __init__(self, status, detail, api_key):
        super().__init__(f"Image API returned HTTP {status}: {redact(detail, api_key)[:2000]}")


SETUP_HINT = (
    "Set the missing variable(s) in your shell and retry (values are never printed):\n"
    '  export OPENAI_BASE_URL="https://your-provider.example/v1"\n'
    '  export OPENAI_API_KEY="<your key>"\n'
    "Add the exports to your shell profile (e.g. ~/.zshrc) to make them persistent."
)


def load_config():
    missing = [
        name for name in ("OPENAI_BASE_URL", "OPENAI_API_KEY")
        if not os.environ.get(name, "").strip()
    ]
    if missing:
        raise ValueError(f"{' and '.join(missing)} not set.\n{SETUP_HINT}")
    return os.environ["OPENAI_BASE_URL"].strip(), os.environ["OPENAI_API_KEY"].strip()


def generation_endpoint(base_url):
    return f"{base_url.rstrip('/')}/images/generations"


def build_payload(prompt, args):
    payload = {"model": args.model, "prompt": prompt, "n": 1, "size": args.size}
    # quality and response_format are not accepted by every provider or model
    # (e.g. OpenAI's gpt-image-1 rejects response_format), so send them only
    # when explicitly requested.
    if args.quality:
        payload["quality"] = args.quality
    if args.response_format:
        payload["response_format"] = args.response_format
    return payload


def start_heartbeat(label, interval=30):
    """Print a liveness note to stderr every `interval` seconds until stopped.

    Relay providers can take minutes to respond; without output, a supervising
    agent cannot tell a slow request from a hung one.
    """
    stop = threading.Event()

    def beat():
        elapsed = 0
        while not stop.wait(interval):
            elapsed += interval
            print(f"note: still waiting for {label} ({elapsed}s elapsed)...", file=sys.stderr, flush=True)

    threading.Thread(target=beat, daemon=True).start()
    return stop


def api_request(base_url, api_key, payload, timeout):
    request = urllib.request.Request(
        generation_endpoint(base_url),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    print("note: request sent; generation through relay providers can take several minutes...",
          file=sys.stderr, flush=True)
    stop = start_heartbeat("the image API")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise ApiError(error.code, detail, api_key) from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Unable to reach image API: {redact(str(error.reason), api_key)}") from error
    finally:
        stop.set()


def download_image(url, timeout=300):
    request = urllib.request.Request(url, headers={"Accept": "image/*", "User-Agent": USER_AGENT})
    stop = start_heartbeat("the image download")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    finally:
        stop.set()


def extract_image_bytes(response):
    images = response.get("data") or []
    if not images:
        raise ValueError(f"Image API returned no image data: {json.dumps(response)[:1000]}")
    image = images[0]
    if image.get("b64_json"):
        try:
            return base64.b64decode(image["b64_json"], validate=True)
        except ValueError as error:  # binascii.Error subclasses ValueError
            raise ValueError("Image API returned invalid base64 data.") from error
    if image.get("url"):
        return download_image(image["url"])
    raise ValueError("Image response contains neither 'b64_json' nor 'url'.")


def jpeg_dimensions(data):
    offset = 2
    while offset + 4 <= len(data):
        if data[offset] != 0xFF:
            return None
        marker = data[offset + 1]
        if marker == 0xFF:  # fill byte before a marker
            offset += 1
            continue
        if marker == 0x01 or 0xD0 <= marker <= 0xD7:  # standalone, no length field
            offset += 2
            continue
        if marker in (0xD9, 0xDA):  # EOI / SOS: no frame header seen before scan data
            return None
        segment_length = struct.unpack(">H", data[offset + 2:offset + 4])[0]
        if segment_length < 2:
            return None
        if marker in JPEG_SOF_MARKERS:
            if offset + 9 > len(data):
                return None
            height, width = struct.unpack(">HH", data[offset + 5:offset + 9])
            return width, height
        offset += 2 + segment_length
    return None


def webp_dimensions(data):
    chunk = data[12:16]
    if chunk == b"VP8X" and len(data) >= 30:
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
        return width, height
    if chunk == b"VP8 " and len(data) >= 30 and data[23:26] == b"\x9d\x01\x2a":
        width = int.from_bytes(data[26:28], "little") & 0x3FFF
        height = int.from_bytes(data[28:30], "little") & 0x3FFF
        return width, height
    if chunk == b"VP8L" and len(data) >= 25 and data[20] == 0x2F:
        bits = int.from_bytes(data[21:25], "little")
        width = (bits & 0x3FFF) + 1
        height = ((bits >> 14) & 0x3FFF) + 1
        return width, height
    return None


def image_info(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return "PNG", width, height
    if data.startswith(b"\xff\xd8"):
        dimensions = jpeg_dimensions(data)
        if dimensions:
            return ("JPEG",) + dimensions
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        dimensions = webp_dimensions(data)
        if dimensions:
            return ("WebP",) + dimensions
    raise ValueError("Response is not a recognized PNG, JPEG, or WebP image.")


def write_validated_image(data, output):
    image_format, width, height = image_info(data)
    if width <= 0 or height <= 0:
        raise ValueError("Image dimensions must be positive.")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    return {
        "path": str(output.resolve()),
        "format": image_format,
        "width": width,
        "height": height,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def parse_args():
    parser = argparse.ArgumentParser(description="Generate an image through an OpenAI-compatible API.")
    prompt_source = parser.add_mutually_exclusive_group(required=True)
    prompt_source.add_argument("--prompt")
    prompt_source.add_argument("--prompt-file", type=Path, help="Read the prompt from a UTF-8 text file.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default=os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1"))
    parser.add_argument("--size", default="1024x1024")
    parser.add_argument("--quality", default=None, choices=("low", "medium", "high", "auto"),
                        help="Omitted from the request unless set.")
    parser.add_argument("--response-format", default=None, choices=("b64_json", "url"),
                        help="Omitted from the request unless set.")
    parser.add_argument("--timeout", type=int, default=600,
                        help="HTTP timeout in seconds for the generation request (default: 600).")
    return parser.parse_args()


def resolve_prompt(args):
    if args.prompt_file:
        prompt = args.prompt_file.read_text(encoding="utf-8").strip()
    else:
        prompt = (args.prompt or "").strip()
    if not prompt:
        raise ValueError("Prompt must not be empty.")
    return prompt


def main():
    args = parse_args()
    api_key = ""
    try:
        prompt = resolve_prompt(args)
        base_url, api_key = load_config()
        response = api_request(base_url, api_key, build_payload(prompt, args), args.timeout)
        metadata = write_validated_image(extract_image_bytes(response), args.output)
        print(json.dumps(metadata, ensure_ascii=False))
    except (OSError, RuntimeError, ValueError, urllib.error.URLError) as error:
        print(f"error: {redact(str(error), api_key)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
