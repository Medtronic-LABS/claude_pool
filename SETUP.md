# claude_pool setup

`claude_pool` lets you juggle several Claude Code accounts on one machine. Each
account gets its own isolated config directory under `profiles/<name>/`, listed
in `accounts.json`. The `claudes` command launches `claude` with
`CLAUDE_CONFIG_DIR` pointed at the right profile, and can report each
account's session/weekly usage so you can pick the least-used one.

## Prerequisites

- macOS with `zsh` or `bash`
- `python3` (and `pip`) on PATH
- The `claude` CLI installed, and already logged in once per account you plan to add

## Setup

```bash
./setup.sh
```

This installs any packages listed in `requirements.txt` (none yet — the
tooling is stdlib-only today), then runs `claudes.py install` to create `~/.claudes` (profiles dir +
`accounts.json`) and put a `claudes` command on PATH. If `/usr/local/bin`
isn't writable (no sudo), the script automatically falls back to
`~/bin/claudes` and adds it to PATH in your shell rc file — restart your
terminal (or `source` the rc file) afterwards.

You can install manually instead, if you prefer:

```bash
python3 claudes.py install
```

## Verify

```bash
claudes list
```

## Adding an account

```bash
claudes add <name>
```

This creates `profiles/<name>/` and then automatically launches `claude`
with `CLAUDE_CONFIG_DIR` pointed at that profile, so you can complete the
login flow right away — its credentials/session land in that profile
directory.

### Example

Adding an account named `alice` after `./setup.sh` has already been run:

```bash
$ claudes add alice
Added alice
Launching claude to log in...
# complete the normal Claude Code login flow, then exit

$ claudes list
alice

$ claudes launch alice
```

## Commands

| Command                  | Description                                              |
|---------------------------|-----------------------------------------------------------|
| `claudes list`             | List configured accounts                                  |
| `claudes launch <name>`    | Launch `claude` using that account's config (alias: `switch`) |
| `claudes usage`            | Show session/weekly usage % for every account              |
| `claudes best`             | Print the name of the least-used account                   |
| `claudes switch-best`      | Launch `claude` using the least-used account                |
| `claudes migrate`          | Link accounts (and the default `~/.claude` config) into the shared session layer, importing historical data |

`best`/`switch-best` print a live log to stderr as each account's usage
is checked (session %, weekly %, and the weighted score), then a line
explaining which account won and why. `claudes best`'s stdout stays just
the account name, so it's still safe to compose, e.g.
`claudes launch $(claudes best)`.

## Shared session context

Every profile normally has its own `projects/`, `plugins/`, `cache/`,
`history.jsonl`, and `settings.json` — meaning if you started a project
under `alice` and later switched to `bob`, `bob` wouldn't know that
project or session existed.

`claude_pool` avoids that by keeping one copy of those files in
`<CLAUDES_BASE>/shared/`, and replacing the per-profile copies with
symlinks into it. Every account reads and writes the same project
history, shell history, plugin state, cache, and settings — so switching
accounts to work around a usage limit doesn't cost you your context.
`claudes launch`/`switch` also updates each project's "last session" in
the account's `.claude.json` before launching, so resuming a project
(`claude -c` / picking it from the project list) picks up the most recent
session regardless of which account you resume it from.

New accounts get wired into the shared layer automatically —
`claudes add <name>` calls this as part of creating the profile, so
there's usually nothing extra to do.

### Importing existing sessions

If you already had accounts set up before this feature existed (or ran
`claude` directly under `~/.claude` before adopting `claude_pool`), run:

```bash
claudes migrate
```

This will:

1. For every registered account, and for the default `~/.claude` config
   (used whenever you run plain `claude` without `CLAUDE_CONFIG_DIR` set)
   — skip it if a `claude` process is currently active under it (finish or
   exit that session first, then re-run `claudes migrate`).
2. Otherwise, move its existing `projects/`, `plugins/`, `cache/`,
   `history.jsonl`, and `settings.json` into `<CLAUDES_BASE>/shared/`
   (merging rather than overwriting anything already shared), then
   replace them with symlinks. This means plain `claude` gets folded into
   the shared layer permanently, not just copied once — from then on it
   reads and writes the same shared context as every pool account.
3. Separately, copy in (without deleting) any leftover historical
   session/history data sitting in stale locations from earlier setups —
   old per-account directories directly under `~/.claudes/`, and orphaned
   `~/.claude/<name>` / `~/.claude/profiles/<name>` directories.

It prints how many session files and history entries were imported from
each source, and which profiles (including `~/.claude` itself) got linked.
It's safe to re-run; already-shared or already-imported data is skipped
rather than duplicated.

**Note:** this changes `~/.claude`'s directory structure — `projects/`,
`plugins/`, `cache/`, `history.jsonl`, and `settings.json` become symlinks
into `<CLAUDES_BASE>/shared/`. Nothing else under `~/.claude` (credentials,
etc.) is touched.

## Config

By default the pool lives at `~/.claudes`. Override with `CLAUDES_BASE` to
point it elsewhere (e.g. this repo's own `profiles/` directory):

```bash
export CLAUDES_BASE=/Users/amresh/labs/claude_pool
```

## Troubleshooting

**`claudes: command not found`** — `/usr/local/bin` usually requires sudo to
write to. Re-run `./setup.sh`; it detects this and falls back to
`~/bin/claudes` plus a PATH entry in your shell rc file automatically. Just
make sure to restart your terminal (or `source` the rc file) afterwards.
