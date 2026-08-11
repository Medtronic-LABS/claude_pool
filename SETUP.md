# claude_pool setup

`claude_pool` lets you juggle several Claude Code accounts on one machine. Each
account gets its own isolated config directory under `profiles/<name>/`, listed
in `accounts.json`. Running `claudes` with no arguments checks every account's
session/weekly usage live and shows an arrow-key menu to pick which one to
launch — it launches `claude` with `CLAUDE_CONFIG_DIR` pointed at the chosen
profile.

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
`~/bin/claudes` and adds it to PATH in your shell rc file — then, if run
from a real terminal, relaunches your shell so `claudes` is ready to use
right away, no manual restart needed.

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

This creates `profiles/<name>/` and then immediately runs `claude auth
login` under that profile — the login link gets copied to your clipboard
(see [Logging in](#logging-in) below) rather than opening a browser tab, so
you can paste it into whichever browser you want. Its credentials/session
land in that profile directory.

### Example

Adding an account named `alice` after `./setup.sh` has already been run:

```bash
$ claudes add alice
Added alice
Login link copied to clipboard — paste it into any browser to sign in:
https://claude.ai/... (your actual login URL)
# open that link in a browser, complete login

$ claudes list
alice

$ claudes
```

## Commands

| Command                  | Description                                              |
|---------------------------|-----------------------------------------------------------|
| `claudes`                  | Check every account's session/usage live, then pick one to launch |
| `claudes list`             | List configured accounts                                  |
| `claudes usage`            | Show session/weekly usage % for every account with an active session |
| `claudes migrate`          | Link accounts (and the default `~/.claude` config) into the shared session layer, importing historical data |

`usage` and bare `claudes` check each account for real by running
`claude -p /usage` under its config. Each account gets one line: the
command flashes briefly while it runs, then is replaced in place by the
result — so checking several accounts doesn't scroll the log, but you can
still see what's actually being run. Claude Code sessions can expire and
need a fresh login; a failed/non-zero result is treated as an expired
session (not 0% usage) rather than silently making a logged-out account
look like the best choice. `claudes` then shows an arrow-key menu, e.g.:

```
Checking account sessions and usage...
  ✓ alice        session  12%  week   5%  score   9.9
  ✗ carol        session expired

Recommended: alice — lowest score 9.9 among active sessions (70% session + 30% weekly usage)

Select an account (↑/↓ move, ←/→ switch, Enter choose, q cancel):

Available:                 Login required:
┌─────────────────────┐    ┌─────────────────────┐
│ alice  12%  5%  9.9  │    │ carol (Enter to log in) │  <- selected: bordered + highlighted
└─────────────────────┘    └─────────────────────┘
```

"Available" and "Login required" render side by side when both have
entries (otherwise whichever one exists renders alone, without the
←/→ hint). Use ↑/↓ to move within a column and ←/→ to switch columns; the
selected account is boxed and highlighted (the recommended one starts
pre-selected, so pressing Enter immediately accepts it), then `claudes`
launches `claude` with the chosen account. Accounts under "Login
required" are excluded from the usage comparison; choosing one logs you
in (see below) instead of launching a session, then everything is
re-checked and the menu reappears (now including that account, if login
succeeded). Press `q` to cancel without picking anything. When stdin
isn't a terminal (cron jobs, scripts, pipes), the menu is skipped and the
recommended account launches automatically.

## Logging in

Whenever `claude auth login` needs to run — from `claudes add <name>` for a
brand-new account, or from picking a "Login required" entry in the
menu — `claudes` runs it directly and streams its output live. As soon as
the login URL appears, it's copied to your clipboard (via `pbcopy`) and
printed, instead of letting a browser tab open automatically:

```
Login link copied to clipboard — paste it into any browser to sign in:
https://claude.ai/oauth/authorize?...
```

Paste that link into whichever browser you want (useful if you're signed
into different Google/Okta/etc. accounts in different browsers) and
complete the login there; `claudes` keeps waiting and prints the result
once it's done. Browser auto-open is suppressed on a best-effort basis
only (`BROWSER=true` in the subprocess's environment) — if `claude` opens
one directly regardless, the copied link is still there as the reliable
fallback.

Changed your mind, or picked the wrong account? Press **Esc twice** while
it's waiting to cancel the login and go straight back to the account
menu — no need to wait it out or Ctrl-C the whole `claudes` process.

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
Launching an account via `claudes` also updates each project's "last
session" in the account's `.claude.json` first, so resuming a project
(`claude -c` / picking it from the project list) picks up the most recent
session regardless of which account you launched.

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
`~/bin/claudes` plus a PATH entry in your shell rc file automatically. When
run from a real terminal, it then relaunches your shell (`exec "$SHELL"
-li`) so `claudes` is ready to use immediately — no restart needed. If
`setup.sh` was run non-interactively (piped stdin, CI, etc.), it instead
prints `Restart your terminal (or run: source <rc file>)`; do that manually
in that case.
