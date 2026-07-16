# openai-compatible-imagegen

An agent skill that generates images through any OpenAI-compatible
`/images/generations` endpoint (OpenAI itself, sub2api, one-api, or any
self-hosted gateway). Ships with a dependency-free Python client — no `pip
install` needed, only Python 3.8+.

Works with Claude Code and Codex CLI.

## Quick Install

### Option A — one-liner

```bash
curl -fsSL https://raw.githubusercontent.com/beansmile/openai-compatible-imagegen/main/install.sh | bash
```

The installer auto-detects Claude Code and/or Codex CLI and installs into
every harness it finds. To pick explicitly, append flags (combinable):

```bash
curl -fsSL https://raw.githubusercontent.com/beansmile/openai-compatible-imagegen/main/install.sh | bash -s -- --claude    # ~/.claude/skills/
curl -fsSL https://raw.githubusercontent.com/beansmile/openai-compatible-imagegen/main/install.sh | bash -s -- --codex     # ${CODEX_HOME:-~/.codex}/skills/
curl -fsSL https://raw.githubusercontent.com/beansmile/openai-compatible-imagegen/main/install.sh | bash -s -- --project   # ./.claude/skills/ (this project only)
```

Re-running the installer updates an existing install (`git pull`).

If HTTPS access to github.com is unreliable from your network, point the
installer at the SSH URL or a mirror:

```bash
curl -fsSL <installer-url-or-local-path> | IMAGEGEN_REPO_URL="git@github.com:beansmile/openai-compatible-imagegen.git" bash
```

### Option B — let your agent install it

Paste this into your Claude Code / Codex session:

> Install the agent skill from
> https://github.com/beansmile/openai-compatible-imagegen — fetch its README
> and follow the "For AI agents" section.

### Option C — manual

Clone into your harness's skills folder yourself:

| Harness | Destination |
| --- | --- |
| Claude Code (personal) | `~/.claude/skills/openai-compatible-imagegen` |
| Claude Code (this project) | `.claude/skills/openai-compatible-imagegen` |
| Codex CLI | `${CODEX_HOME:-$HOME/.codex}/skills/openai-compatible-imagegen` |

```bash
git clone https://github.com/beansmile/openai-compatible-imagegen.git ~/.claude/skills/openai-compatible-imagegen
```

Already have the repo locally? `cp -R` it to the same destination instead of
cloning.

### For AI agents

If you are an AI agent installing this skill on a user's behalf:

1. Pick the destination from the table above based on the harness you are
   running in (personal install unless the user asked for project-level).
2. Run: `git clone --depth 1 https://github.com/beansmile/openai-compatible-imagegen.git <destination>`
   — or, if the destination already exists as a git checkout, `git -C <destination> pull --ff-only`.
3. Verify: `python3 -m unittest discover <destination>/tests` should report all
   tests passing.
4. Check credentials **without printing their values**:
   `[[ -n "$OPENAI_BASE_URL" && -n "$OPENAI_API_KEY" ]]`. If either is missing,
   show the user the `export` lines from "Configure Credentials" below and ask
   them to set the variables locally — never ask them to paste a key into chat.
5. Tell the user the skill is installed and, if needed, that they should
   restart the session so the new skill and environment variables are picked up.

## Configure Credentials

The skill reads two environment variables. Set them in your shell **before**
starting your agent session, and never paste the key into the chat itself:

```bash
export OPENAI_BASE_URL="https://your-provider.example/v1"
export OPENAI_API_KEY="<your key>"
```

Optional:

```bash
export OPENAI_IMAGE_MODEL="gpt-image-2"   # default model; override per-request with --model
export OPENAI_IMAGE_SIZE="832x832"        # default size; override per-request with --size
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

Options: `--model` (default `gpt-image-2`), `--size` (default `832x832`),
`--quality`, `--response-format`, `--prompt-file` (for prompts with tricky
quoting), `--timeout` (seconds, default 600). `--quality` and
`--response-format` are only sent to the API when explicitly passed, since
not every provider accepts them.

Note on sizes: `gpt-image-2` accepts arbitrary `WIDTHxHEIGHT` (both divisible
by 16); `gpt-image-1` only accepts `1024x1024`, `1536x1024`, or `1024x1536`,
so pass one of those explicitly if you switch the model to it.

Generation through relay providers can take several minutes. The client
prints a progress note to stderr every 30 seconds while waiting, so a slow
request is distinguishable from a hung one.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `OPENAI_BASE_URL … not set` | Run the printed `export` lines, restart the agent session so it inherits them. |
| Process killed after ~1-2 min with no output | Your agent's command timeout fired, not a client error. Rerun with a longer timeout or in a background/persistent shell. |
| HTTP 400 about an unknown parameter | Drop the optional flag (`--quality` / `--response-format`) you passed. |
| HTTP 401 / 403 | Key is wrong or lacks image permission on your gateway. |
| Cloudflare 403 / error 1010 | The client already sends a browser User-Agent; if it persists, the block is provider-side. |
| "not a recognized PNG, JPEG, or WebP" | The endpoint returned non-image content (often an HTML error page); nothing was saved. |

Error output always redacts your API key.

## Development

```bash
python3 -m unittest discover tests
```
