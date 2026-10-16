# CodeDuo

**A local collaboration workbench for Codex × CodeBuddy.**

[简体中文](README.md) · [Setup](docs/SETUP.md) · [Privacy](docs/PRIVACY.md)

CodeDuo connects your locally installed Codex CLI and CodeBuddy Code CLI in one browser interface. Codex advances the task, CodeBuddy independently reviews the evidence, and subsequent rounds address concrete findings. This is an independent community project, unaffiliated with OpenAI or Tencent.

![Synthetic CodeDuo demonstration](docs/images/workbench.png)

## What it does

- Ordered handoffs, up to three rounds, or a single-agent response.
- Streaming messages, tool activity, plans, code diffs and draft line feedback.
- Human questions, message queues, interrupt/continuation and acknowledged follow-ups.
- Per-conversation permissions, model selection, working directory and task list.
- File references, uploads, exports, summaries and original-context archives.
- Reported token usage and credits, with unavailable values clearly distinguished.
- In-process coordination for shared project/device writes; this is not an OS sandbox.

## Run locally

Windows 10/11 is the primary target. Install Python 3.12+, Node.js and Codex CLI, then sign in using your own accounts. Other operating systems are not fully validated.

```sh
git clone https://github.com/fhw0830/codex-codebuddy-workbench.git
cd codex-codebuddy-workbench
npm install -g @openai/codex
codex login
python scripts/prepare_runtime.py
```

The preparation script prints the pinned CodeBuddy `2.164.0` entry point in your user cache. Run that entry point with Node.js and follow the CLI's own authentication flow. Alternatively configure an already-installed entry point in `config.local.json`.

```sh
python server.py --open
```

On Windows, `Start-CodeDuo.cmd` is also available. No login startup task is installed. The default address is `http://127.0.0.1:8766`; the selected port is written to `data/server.json`.

To preview the interface without launching either agent CLI:

```sh
python server.py --offline --open
```

Start in discussion mode, confirm both connections/models, and explicitly select your working directory before enabling full access. The UI is currently primarily Chinese.

## Data and access

Runtime data is local under `data/` and ignored by Git. Requests, selected files and conversation context sent to an agent are processed by its provider through that CLI. Local storage does not imply offline inference. The public snapshot includes no original conversations, credentials, logs or project documents.

Full access can run local tools and commands. Do not expose this personal loopback service to a public network: there is no multi-user authentication system. Stopping a job does not undo file writes. Web conversations do not synchronize with desktop application chats.

## Verify

```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -p "test_*.py"
python scripts/run_js_tests.py
python scripts/privacy_check.py
```

Full regression tests install optional attachment-format dependencies through `requirements-dev.txt`. The core text service needs only the standard library; image validation and some document readers are optional. These checks use temporary data and synthetic adapters. They do not establish live inference compatibility for every model/account. No frontend build or npm install is required for the vendored browser assets.

Original source: [MIT](LICENSE). See [third-party notices](THIRD_PARTY_NOTICES.md) for bundled assets. Model access and external CLI licenses remain separate.
