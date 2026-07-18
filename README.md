# MorrowHelm

> Steer the company you're becoming.

MorrowHelm is an open-source, local-first command deck for running a capable
one-person company with AI employees. It turns agent work into a mobile control
loop where the founder can delegate, inspect, approve, and stay accountable.

> **Six Codex agents move the company forward. You keep the final say.**

## Why MorrowHelm?

The name joins **morrow**—the coming day or future—with **helm**, the place from
which a vessel is steered. It represents one founder directing an intelligent
company toward what comes next.

## What it does

The mobile-first PWA gives a founder one place for:

- talking with synthetic virtual employees;
- turning conversations into inspectable tasks;
- reviewing approvals with side effects, scopes, risk, spend, and reversibility;
- approving or rejecting with optimistic version checks;
- keeping an append-only activity trail;
- launching a real sprint trace: five specialists work in parallel, then a
  Chief of Staff synthesizes their outputs into one decision brief;
- previewing inspectable artifacts from isolated agent workspaces;
- connecting an OpenAI-compatible gateway, CrewAI adapter, A2A adapter, or
  generic webhook by storing an API key in an encrypted local vault.

All seeded people, tasks, artifacts, and approvals are synthetic demo data.

The demo company is **LumenDesk Studio**, a tiny product studio launching a
calm planning tool for solo consultants. The seeded team is generated with
synthetic names and roles for chief of staff, research, product, growth,
finance, and operations. Every employee has a separate Codex CLI run profile
and an isolated workspace under `.data/agents/<employee>/<run>`.

## Run locally

```bash
uv sync --extra dev
cp .env.example .env
uv run morrowhelm
```

Open <http://127.0.0.1:8787>. The default development password is
`change-me-now`; set `MORROWHELM_PASSWORD` before sharing the service through a
tunnel or VPN. Local runtime data is written to `.data/`, which is ignored by
Git. The first start generates `.data/master.key` and encrypts saved provider
keys in `.data/secrets.bin`.

For a deterministic public demo, set `MORROWHELM_DEMO_MODE=replay`. Replay mode
creates synthetic Codex-labelled runs, real local Markdown artifacts, a
Chief-of-Staff synthesis, and a Founder Gate approval without requiring a live
CLI session. `auto` (the default) uses Codex when available and falls back to
replay; `live` requires the Codex CLI.

For a phone, keep the server bound to the host machine and use an HTTPS tunnel
or a private VPN. Set `MORROWHELM_COOKIE_SECURE=true` when the public URL is
HTTPS.

## Codex CLI demo runtime

The one-person-company demo can run each virtual employee as a local Codex CLI
agent. First verify the CLI is installed and authenticated:

```bash
codex --version
codex login
```

Then launch MorrowHelm and press **Launch a full sprint** on the home screen.
The server dispatches five isolated Codex runs in parallel, waits for their
results, then dispatches the Chief of Staff synthesis in a separate workspace.
It stores result summaries and inspectable artifacts, and turns any explicit
external-action request into a founder approval. The CLI runtime uses the
configured ChatGPT login and does not need an OpenAI API key. To disable it for
offline tests, set
`MORROWHELM_CODEX_COMMAND` to a non-existent executable.

## Adapter boundary

The app core does not call a model directly. Runtimes send normalized events
with the shape in `adapters/base.py` and submit a complete approval manifest
through `protocol.py`. An approval decision is valid only for the exact
`action_hash` and version shown to the founder. A connected executor should
return a receipt containing the action hash, external IDs, actual side effects,
and final status.

Reference adapters are deliberately small and offline-friendly. A production
adapter can translate CrewAI events, A2A tasks/messages/artifacts, an
OpenAI-compatible gateway, or a signed webhook into the same event contract.

## Development checks

```bash
uv run pytest
```

The tests cover authentication boundaries, task creation, approval version
checks, action-hash stability, and the guarantee that API keys are never
returned from the API.

## Privacy and repository boundary

- Runtime state and encrypted provider credentials stay under the ignored
  `.data/` directory.
- Environment files, keys, local databases, and generated output are ignored.
- The repository has no parent-directory imports or private infrastructure
  assumptions.
- External systems connect only through the documented adapter boundary.

## License

MorrowHelm is released under the [MIT License](LICENSE).
