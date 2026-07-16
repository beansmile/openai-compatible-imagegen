# openai-compatible-imagegen

An agent skill that generates images through any OpenAI-compatible
`/images/generations` endpoint (OpenAI itself, sub2api, one-api, or any
self-hosted gateway). Ships with a dependency-free Python client — no `pip
install` needed, only Python 3.8+.

Works with Claude Code and Codex CLI.

## Quick Install

Copy (or clone) this directory into your agent's skills folder:

**Claude Code** (personal, available in every project):

```bash
git clone https://github.com/beansmile/openai-compatible-imagegen.git ~/.claude/skills/openai-compatible-imagegen
```

or, for a single project:

```bash
git clone https://github.com/beansmile/openai-compatible-imagegen.git .claude/skills/openai-compatible-imagegen
```

**Codex CLI:**

```bash
git clone https://github.com/beansmile/openai-compatible-imagegen.git "${CODEX_HOME:-$HOME/.codex}/skills/openai-compatible-imagegen"
```

Already have the repo locally? `cp -R` it to the same destination instead of
cloning.

## Configure Credentials

The skill reads two environment variables. Set them in your shell **before**
starting your agent session, and never paste the key into the chat itself:

```bash
export OPENAI_BASE_URL="https://your-provider.example/v1"
export OPENAI_API_KEY="<your key>"
```

Optional:

```bash
export OPENAI_IMAGE_MODEL="gpt-image-1"   # default model; override per-request with --model
```

Add the exports to your shell profile (`~/.zshrc`, `~/.bashrc`, …) to make
them persistent, then restart the agent session so it inherits them.

> **Forgot to set them?** Nothing breaks — the client detects exactly which
> variable is missing and prints the `export` lines to run, and the agent will
> relay those instructions to you. Your key's value is never printed or logged.

## Usage

Just ask your agent, e.g.:

> Generate an image of a lighthouse at dusk, watercolor style.

The agent invokes the skill, calls your endpoint, validates that the response
is a real PNG/JPEG/WebP, saves it under `outputs/`, and reports the path,
dimensions, byte size, and SHA-256.

You can also run the client directly:

```bash
python3 scripts/generate_image.py \
  --prompt 'a lighthouse at dusk, watercolor' \
  --output outputs/lighthouse.png
```

Options: `--model`, `--size` (default `1024x1024`), `--quality`,
`--response-format`, `--prompt-file` (for prompts with tricky quoting).
`--quality` and `--response-format` are only sent to the API when explicitly
passed, since not every provider accepts them.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `OPENAI_BASE_URL … not set` | Run the printed `export` lines, restart the agent session so it inherits them. |
| HTTP 400 about an unknown parameter | Drop the optional flag (`--quality` / `--response-format`) you passed. |
| HTTP 401 / 403 | Key is wrong or lacks image permission on your gateway. |
| Cloudflare 403 / error 1010 | The client already sends a browser User-Agent; if it persists, the block is provider-side. |
| "not a recognized PNG, JPEG, or WebP" | The endpoint returned non-image content (often an HTML error page); nothing was saved. |

Error output always redacts your API key.

## Development

```bash
python3 -m unittest discover tests
```
