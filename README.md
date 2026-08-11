# claude_pool

A small CLI for juggling multiple Claude Code accounts on one machine.

Claude Code's usage limits are per-account. If you have access to more than
one account, `claude_pool` lets you keep each one in its own isolated config
directory and switch between them with a single command — including picking
whichever account currently has the most headroom left.

## How it works

- Each account is a named entry in `accounts.json`, pointing at its own
  config directory under `profiles/<name>/`.
- The `claudes` CLI (`claudes.py`) launches `claude` with `CLAUDE_CONFIG_DIR`
  set to that account's profile, so credentials, sessions, and settings
  never mix between accounts.
- It can also poll each account's `/usage` output and report session/weekly
  usage %, so you can jump to (or auto-launch) whichever account is least
  used.
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
| `claudes add <name>`     | Register a new account, create its profile directory, and launch `claude` to log in |
| `claudes list`           | List configured accounts                                         |
| `claudes launch <name>`  | Launch `claude` using that account's config (alias: `switch`)    |
| `claudes usage`          | Show session/weekly usage % for every account                    |
| `claudes best`           | Print the name of the least-used account                         |
| `claudes switch-best`    | Launch `claude` using the least-used account                     |
| `claudes migrate`        | Link existing accounts (and the default `~/.claude` config) into the shared session layer, importing historical data |

`best`/`switch-best` log each account's session/weekly usage and score to
stderr as they're checked, then explain why the winner was picked — so
`claudes best` still prints just the account name on stdout (safe to use
in scripts, e.g. `claudes launch $(claudes best)`) while the reasoning is
visible live in the terminal.

## Quick start

```bash
./setup.sh
claudes add <name>
claudes list
```

See [SETUP.md](SETUP.md) for full installation steps, prerequisites, and
troubleshooting.

## Project layout

- `claudes.py` — the `claudes` CLI (stdlib-only, no third-party deps)
- `setup.sh` — installer; wires up `requirements.txt`, runs `claudes.py install`, and falls back to a no-sudo PATH setup if needed
- `requirements.txt` — Python dependencies (currently none)
- `accounts.json`, `profiles/`, `shared/` — local per-machine account state, per-account Claude configs, and the cross-account shared session layer; gitignored, never committed
