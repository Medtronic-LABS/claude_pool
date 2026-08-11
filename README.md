# claude_pool

A small CLI for juggling multiple Claude Code accounts on one machine.

Claude Code's usage limits are per-account. If you have access to more than
one account, `claude_pool` lets you keep each one in its own isolated config
directory and pick which one to use with a single command — with live usage
info to help you choose.

## How it works

- Each account is a named entry in `accounts.json`, pointing at its own
  config directory under `profiles/<name>/`.
- Running `claudes` with no arguments checks every account's session and
  usage live, then shows an arrow-key menu so you pick which one to launch
  — it recommends the least-used account but the choice is yours.
- The `claudes` CLI (`claudes.py`) launches `claude` with `CLAUDE_CONFIG_DIR`
  set to that account's profile, so credentials, sessions, and settings
  never mix between accounts.
- Project history, plugins, cache, shell history, and settings are shared
  across every account via a `shared/` layer (symlinked into each profile),
  so switching accounts doesn't mean losing track of what you were doing —
  resuming a project picks up the latest session no matter which account
  you launch it from. `claudes migrate` can fold plain `claude` (the
  default `~/.claude` config) into this shared layer too.

## Commands

| Command                 | Description                                                    |
|--------------------------|------------------------------------------------------------------|
| `claudes install`        | Set up `~/.claudes` and put the `claudes` command on PATH        |
| `claudes add <name>`     | Register a new account, create its profile directory, and start login |
| `claudes`                | Check every account's session/usage live, then pick one to launch |
| `claudes list`           | List configured accounts                                         |
| `claudes usage`          | Show session/weekly usage % for every account with an active session |
| `claudes migrate`        | Link existing accounts (and the default `~/.claude` config) into the shared session layer, importing historical data |

Running bare `claudes` checks each account by actually running
`claude -p /usage` under its config — the command flashes on one line while
it runs, then is replaced in place by the result, so checking several
accounts stays a compact one-line-each log — and treats a failed/non-zero
result as an expired session rather than 0% usage (Claude Code sessions can
expire and need a fresh login). It then shows an arrow-key menu (↑/↓ move,
←/→ switch column, Enter choose, q cancel) with active accounts under
"Available" and expired ones under "Login required" — side by side when
both exist, best score pre-selected. Picking a login-required account
runs `claude auth login` directly and copies the login link to your
clipboard instead of opening a browser tab, so you can paste it into
whichever browser you want (press Esc twice while it's waiting to cancel
and pick a different account); everything is then re-checked and the menu
shown again. When stdin isn't a terminal (cron, scripts, pipes), the menu
is skipped and the recommended account launches automatically.

## Quick start

```bash
./setup.sh
claudes add <name>
claudes
```

See [SETUP.md](SETUP.md) for full installation steps, prerequisites, and
troubleshooting.

## Project layout

- `claudes.py` — the `claudes` CLI (stdlib-only, no third-party deps)
- `setup.sh` — installer; wires up `requirements.txt`, runs `claudes.py install`, and falls back to a no-sudo PATH setup if needed
- `requirements.txt` — Python dependencies (currently none)
- `accounts.json`, `profiles/`, `shared/` — local per-machine account state, per-account Claude configs, and the cross-account shared session layer; gitignored, never committed
