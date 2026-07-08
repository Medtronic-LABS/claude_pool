# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`claude_pool` is a small CLI (`claudes.py`) for running multiple Claude Code
accounts on one machine, each with its own isolated config directory, and
switching between them based on which account has the most usage headroom
left. See README.md for the user-facing overview and SETUP.md for full
install/usage docs — don't duplicate that content here.

## Commands

There is no build step, package manifest, lint config, or test suite in this
repo — it's a couple of stdlib-only Python scripts plus a bash installer.

- Install/repair the `claudes` shortcut: `./setup.sh`
- Run the CLI directly during development: `python3 claudes.py <command>`
  (e.g. `python3 claudes.py list`, `python3 claudes.py add <name>`)
- Sanity-check the installer after editing it: `bash -n setup.sh`
- Confirm no accidental third-party imports were introduced:
  `grep -rn "^import\|^from" claudes.py claude_pool.py` and check each
  module name against `python3 -c "import sys; print(sys.stdlib_module_names)"`
  — `requirements.txt` should stay empty unless a real third-party import
  is added.

## Architecture

- **Account model**: `accounts.json` is a list of `{name, config_path}`
  entries. Each account's Claude Code state (credentials, sessions,
  settings) lives under `profiles/<name>/`. Switching accounts means
  invoking `claude` with `CLAUDE_CONFIG_DIR` set to that account's
  `config_path` — there's no other isolation mechanism.
- **`claudes.py` is the one live entry point.** It resolves its base
  directory as `CLAUDES_BASE` (env var) or `~/.claudes`, and everything
  (`accounts.json`, `profiles/`, the installed `claudes` copy of itself)
  hangs off that base. Command dispatch is a flat `if/elif` on `sys.argv[1]`
  at the bottom of the file — add new subcommands there.
- **`claude_pool.py` is a dead/legacy installer draft.** It defines its own
  `install()` with slightly different behavior (adds a `logs/` dir, tries a
  `~/bin` fallback, edits `.zshrc` directly) but has no `if __name__` /
  arg-parsing block, so nothing calls it. Don't assume it runs — if
  install behavior needs to change, change `claudes.py`'s `install()` (and
  port over anything still useful from `claude_pool.py`), then consider
  deleting `claude_pool.py`.
- **`setup.sh` is the recommended install path**, not a thin wrapper you
  can ignore: it installs `requirements.txt` deps, runs
  `claudes.py install`, and then — because `/usr/local/bin` commonly isn't
  writable without sudo — falls back to symlinking `~/bin/claudes` and
  appending a PATH export to the user's shell rc file
  (`.zshrc`/`.bash_profile`/`.profile` based on `$SHELL`). Any change to
  how `claudes.py install()` behaves should be re-checked against this
  fallback path.
- **`accounts.json` and `profiles/` are gitignored** and hold live,
  per-machine state (account assignment metadata, real Claude credentials
  and session history). Never add example/sample data for these into the
  repo, and never suggest committing them — the copies in the working
  directory are real, in-use data, not fixtures.
- **`CLAUDES_BASE` is a load-bearing override**, not just a convenience: on
  at least one real setup, `accounts.json` entries' `config_path` values
  point back into this repo's own `profiles/` directory instead of
  `~/.claudes/profiles/`, meaning this repo can itself be the pool's base
  directory rather than just the source of the installer. Don't assume
  `~/.claudes` is the only place account state lives.
