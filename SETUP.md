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
| `claudes migrate`          | Link accounts into the shared session layer and import historical sessions |

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

This will, for every registered account:

1. Skip any profile with an active `claude` process (finish or exit that
   session first, then re-run `claudes migrate`).
2. Move each profile's existing `projects/`, `plugins/`, `cache/`,
   `history.jsonl`, and `settings.json` into `<CLAUDES_BASE>/shared/`
   (merging rather than overwriting anything already shared), then
   replace them with symlinks.
3. Import historical session/history data from stale locations — old
   per-account directories directly under `~/.claudes/`, and `~/.claude`
   (Claude Code's default config dir, including any pre-`claude_pool`
   sessions) — without deleting the originals.

It prints how many session files and history entries were imported from
each source. It's safe to re-run; already-shared or already-imported data
is skipped rather than duplicated.

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
