---
name: openai-compatible-imagegen
description: Use when a user requests image generation through a custom OpenAI-compatible endpoint, mentions sub2api or OPENAI_BASE_URL, or needs an API fallback because built-in image generation is unavailable.
---

# OpenAI-Compatible Image Generation

Generate one raster image through credentials exposed by the user. Use the
bundled dependency-free client at `scripts/generate_image.py`, resolved
relative to this skill's own directory (the directory containing this
SKILL.md); do not create a new API wrapper for each task.

## Credential Rules

- Read `OPENAI_BASE_URL` and `OPENAI_API_KEY` only from the environment.
- Never print, inspect, persist, or interpolate the key into a command string.
- Never ask the user to paste a full key into chat. Ask them to export it locally.
- It is safe to check whether variables are non-empty, but never print values.
- If variables live in shell startup files, source them only after the user says
  they are configured.

## Workflow

1. Shape the user's request into a concise production prompt. Preserve explicit
   subject, style, composition, and constraints.
2. Choose an output path under the current workspace, normally
   `outputs/<descriptive-name>.png`. Do not overwrite an existing file unless
   requested; use a versioned sibling name.
3. Confirm configuration without revealing values:

   ```bash
   [[ -n "$OPENAI_BASE_URL" && -n "$OPENAI_API_KEY" ]]
   ```

4. Run the bundled client. `<skill-dir>` is this skill's directory:

   ```bash
   python3 "<skill-dir>/scripts/generate_image.py" \
     --prompt '<prompt>' \
     --output "<absolute-output-path>"
   ```

   Quote the prompt with single quotes. If the prompt itself contains single
   quotes or other characters that are awkward to escape, write it to a temp
   file instead and pass `--prompt-file <path>`.
5. Read the JSON result and verify the reported path exists. Visually inspect
   the image before claiming success.
6. Display the image using its absolute path and report format, dimensions,
   byte size, SHA-256, final prompt, model, and saved path.

## Provider Compatibility

The client calls `<OPENAI_BASE_URL>/images/generations` and supports responses
containing either `data[0].b64_json` or `data[0].url`. It recognizes PNG,
JPEG, and WebP payloads.

- `--model` defaults to `$OPENAI_IMAGE_MODEL` or `gpt-image-1`; `--size`
  defaults to `1024x1024`.
- `--quality` and `--response-format` are sent only when explicitly passed,
  because not every provider or model accepts them (OpenAI's `gpt-image-1`
  rejects `response_format`, for example). Leave them off unless the user's
  request requires them.

If a provider rejects an optional parameter, report the exact bounded error.
Retry without that parameter only when it is not part of the user's requested
contract. Never silently change providers or models.

## Failure Handling

- Missing variables: the client names the missing variable(s) and prints the
  exact `export` lines to run. Relay those instructions to the user verbatim,
  remind them to restart the session (or re-source their profile) so the
  variables are inherited, and never ask them to paste values into chat.
- HTTP errors: report status and the redacted response excerpt. The client
  redacts the API key from all error output.
- Cloudflare `403 / 1010`: the bundled client already sends a browser-compatible
  user agent; report the remaining provider-side block if it persists.
- Invalid image content: do not save or display it as an image.
- Never fall back to a previous generated file after a failed request.
