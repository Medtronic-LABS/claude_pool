#!/usr/bin/env python3
import json, os, re, select, shutil, stat, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HOME = Path.home()
BASE = Path(os.environ.get("CLAUDES_BASE", HOME / ".claudes")).expanduser()
PROFILES = BASE / "profiles"
ACCOUNTS = BASE / "accounts.json"
CURRENT = BASE / "current_profile"
SHARED = BASE / "shared"

GREEN="\033[92m"; YELLOW="\033[93m"; RED="\033[91m"; GRAY="\033[90m"; RESET="\033[0m"

def ensure():
    BASE.mkdir(exist_ok=True)
    PROFILES.mkdir(exist_ok=True)
    SHARED.mkdir(exist_ok=True)
    for d in ["projects", "plugins", "cache"]:
        (SHARED / d).mkdir(exist_ok=True)
    if not (SHARED / "history.jsonl").exists():
        (SHARED / "history.jsonl").touch()
    if not (SHARED / "settings.json").exists():
        (SHARED / "settings.json").write_text("{}")
    if not ACCOUNTS.exists():
        ACCOUNTS.write_text('{"accounts": []}')

def load():
    ensure()
    return json.loads(ACCOUNTS.read_text())

def save(data):
    ACCOUNTS.write_text(json.dumps(data, indent=2))

def find(name):
    d=load()
    for a in d["accounts"]:
        if a["name"]==name:
            return a
    return None

def config_dir(account):
    path = account.get("config_path") or account.get("path")
    if not path:
        raise KeyError(f"Account {account.get('name', '<unknown>')} has no config_path")
    return path

def _encode_path(abs_path):
    return re.sub(r'[^a-zA-Z0-9]', '-', abs_path)

def _has_active_sessions(profile_path):
    """Return True if any live Claude process is using this profile."""
    sessions_dir = Path(profile_path) / "sessions"
    if not sessions_dir.is_dir():
        return False
    for f in sessions_dir.iterdir():
        if f.suffix == ".json":
            try:
                pid = int(f.stem)
                os.kill(pid, 0)
                return True
            except (ValueError, OSError):
                pass
    return False

def _merge_projects(src_dir, dst_dir, move=False):
    """Merge session .jsonl files from src into dst. Returns count merged."""
    src = Path(src_dir)
    dst = Path(dst_dir)
    if not src.is_dir():
        return 0
    count = 0
    for encoded in src.iterdir():
        if not encoded.is_dir():
            continue
        dst_encoded = dst / encoded.name
        dst_encoded.mkdir(exist_ok=True)
        for f in encoded.iterdir():
            if f.suffix == ".jsonl":
                dst_f = dst_encoded / f.name
                if not dst_f.exists():
                    try:
                        if move:
                            shutil.move(str(f), str(dst_f))
                        else:
                            shutil.copy2(str(f), str(dst_f))
                        count += 1
                    except (OSError, PermissionError):
                        pass
    return count

def _merge_history(src_file, dst_file):
    """Append non-duplicate entries from src to dst. Returns count of new lines."""
    src = Path(src_file)
    dst = Path(dst_file)
    try:
        if not src.is_file() or src.stat().st_size == 0:
            return 0
    except OSError:
        return 0
    seen = set()
    if dst.is_file() and dst.stat().st_size > 0:
        for line in dst.read_text().splitlines():
            try:
                e = json.loads(line)
                seen.add((e.get("sessionId",""), str(e.get("timestamp",""))))
            except Exception:
                pass
    try:
        src_lines = src.read_text().splitlines()
    except OSError:
        return 0
    new_lines = []
    for line in src_lines:
        if not line.strip():
            continue
        try:
            e = json.loads(line)
            key = (e.get("sessionId",""), str(e.get("timestamp","")))
            if key not in seen:
                new_lines.append(line)
                seen.add(key)
        except Exception:
            pass
    if new_lines:
        with open(dst, "a") as f:
            f.write("\n".join(new_lines) + "\n")
    return len(new_lines)

def setup_shared_links(profile_path):
    """Replace portable dirs/files in a profile with symlinks into SHARED."""
    ensure()
    p = Path(profile_path)

    for name in ["projects", "plugins", "cache"]:
        item = p / name
        target = SHARED / name
        if item.is_symlink():
            if item.resolve() == target.resolve():
                continue
            item.unlink()
        elif item.is_dir():
            if name == "projects":
                _merge_projects(item, target, move=True)
            else:
                for child in item.iterdir():
                    dst = target / child.name
                    if not dst.exists():
                        shutil.move(str(child), str(dst))
            try:
                item.rmdir()
            except OSError:
                shutil.rmtree(str(item))
        if not item.exists() and not item.is_symlink():
            item.symlink_to(target)

    for name in ["history.jsonl", "settings.json"]:
        item = p / name
        target = SHARED / name
        if item.is_symlink():
            if item.resolve() == target.resolve():
                continue
            item.unlink()
        elif item.is_file():
            if name == "history.jsonl":
                _merge_history(item, target)
            elif name == "settings.json":
                if target.read_text().strip() in ("{}", ""):
                    shutil.copy2(str(item), str(target))
            item.unlink()
        if not item.exists() and not item.is_symlink():
            item.symlink_to(target)

def _sync_last_session(name):
    """Update lastSessionId per-project in the account's .claude.json."""
    a = find(name)
    if not a:
        return
    cj = Path(config_dir(a)) / ".claude.json"
    if not cj.exists():
        return
    projects_shared = SHARED / "projects"
    if not projects_shared.is_dir():
        return
    try:
        data = json.loads(cj.read_text())
    except Exception:
        return
    projects_map = data.get("projects", {})
    if not projects_map:
        return
    changed = False
    for abs_path, proj in list(projects_map.items()):
        encoded_dir = projects_shared / _encode_path(abs_path)
        if not encoded_dir.is_dir():
            continue
        jsonl_files = [f for f in encoded_dir.iterdir() if f.suffix == ".jsonl"]
        if not jsonl_files:
            continue
        latest = max(jsonl_files, key=lambda f: f.stat().st_mtime)
        uuid = latest.stem
        if proj.get("lastSessionId") != uuid:
            proj["lastSessionId"] = uuid
            changed = True
    if changed:
        cj.write_text(json.dumps(data, indent=2))

def install():
    ensure()
    target = BASE / "claudes"
    shutil.copy2(Path(__file__), target)
    target.chmod(target.stat().st_mode | stat.S_IEXEC)
    link = Path("/usr/local/bin/claudes")
    try:
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to(target)
        print(f"Installed: {link}")
    except Exception:
        print("Add ~/.claudes to PATH manually")
    print("Done")

def add(name):
    d=load()
    if any(a["name"]==name for a in d["accounts"]):
        print("Already exists"); return
    p=PROFILES/name
    p.mkdir(parents=True, exist_ok=True)
    d["accounts"].append({"name":name,"config_path":str(p)})
    save(d)
    setup_shared_links(str(p))
    print("Added", name)
    _login(name)

def list_accounts():
    d=load()
    for a in sorted(d["accounts"], key=lambda x:x["name"]):
        print(a["name"])

def _require_claude():
    if not shutil.which("claude"):
        print(f"{RED}claude CLI not found on PATH{RESET} — install it and log in once per account (see SETUP.md prerequisites).")
        return False
    return True

def launch(name):
    a=find(name)
    if not a:
        print("Not found"); return
    if not _require_claude():
        return
    CURRENT.write_text(name)
    _sync_last_session(name)
    env=os.environ.copy()
    env["CLAUDE_CONFIG_DIR"]=config_dir(a)
    sys.stdout.flush()
    subprocess.run(["claude"], env=env)

_LOGIN_URL_RE=re.compile(r"https?://\S+")

def _login(name):
    """Run `claude auth login` directly under an account's config, so the
    login flow starts immediately instead of requiring /login to be typed
    inside an interactive session. Streams the command's output live; when
    the login URL appears, copy it to the clipboard (via pbcopy) instead of
    letting a browser tab open automatically, so the user can paste it into
    whichever browser they choose. Browser auto-open is only suppressed on
    a best-effort basis (BROWSER=true) — claude may still open one directly;
    the clipboard copy is the reliable part. While waiting, pressing Esc
    twice cancels the login and returns control to the caller."""
    a=find(name)
    if not a:
        print("Not found"); return
    if not _require_claude():
        return
    env=os.environ.copy()
    env["CLAUDE_CONFIG_DIR"]=config_dir(a)
    env["BROWSER"]="true"
    sys.stdout.flush()
    p=subprocess.Popen(["claude","auth","login"], env=env,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

    can_cancel=sys.stdin.isatty()
    copied=False

    def handle_line(line):
        nonlocal copied
        m=_LOGIN_URL_RE.search(line)
        if m and not copied:
            url=m.group(0).rstrip(").,\"'")
            try:
                subprocess.run(["pbcopy"], input=url, text=True, check=True)
                print(f"\n  {GREEN}Login link copied to clipboard{RESET} — paste it into any browser to sign in:")
                print(f"  {url}")
                if can_cancel:
                    print("  (press Esc twice to cancel and pick a different account)")
                print()
                copied=True
                return
            except Exception:
                pass
        print(line, end="")

    old=None; fd=None
    if can_cancel:
        try:
            import termios, tty
            fd=sys.stdin.fileno()
            old=termios.tcgetattr(fd)
            tty.setcbreak(fd)
        except Exception:
            can_cancel=False

    cancelled=False
    last_esc=0.0
    try:
        while True:
            if p.poll() is not None:
                for line in p.stdout:
                    handle_line(line)
                break
            fds=[p.stdout]+([sys.stdin] if can_cancel else [])
            r,_,_=select.select(fds,[],[],0.2)
            if p.stdout in r:
                line=p.stdout.readline()
                if line:
                    handle_line(line)
            if can_cancel and sys.stdin in r:
                ch=sys.stdin.read(1)
                if ch=="\x1b":
                    now=time.time()
                    if now-last_esc<0.75:
                        cancelled=True
                        break
                    last_esc=now
    finally:
        if old is not None:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    if cancelled:
        p.terminate()
        try:
            p.wait(timeout=2)
        except subprocess.TimeoutExpired:
            p.kill()
        print(f"\n  {YELLOW}Login cancelled.{RESET}")
    else:
        p.wait()

def get_usage(name):
    a=find(name)
    if not a: return {"session":0,"week":0,"active":False}
    env=os.environ.copy()
    env["CLAUDE_CONFIG_DIR"]=config_dir(a)
    try:
        r=subprocess.run(["claude","-p","/usage"],capture_output=True,text=True,env=env,timeout=60)
        out=r.stdout
        s=re.search(r"Current session:\s+(\d+)%", out)
        w=re.search(r"Current week.*?:\s+(\d+)%", out)
        if r.returncode!=0 or not s or not w:
            return {"session":0,"week":0,"active":False}
        return {"session":int(s.group(1)),"week":int(w.group(1)),"active":True}
    except Exception:
        return {"session":0,"week":0,"active":False}

def get_usage_all(names):
    """Check every named account's usage concurrently (one thread per
    account, each blocking on its own `claude -p /usage` subprocess).
    Returns a list of usage dicts in the same order as `names`; blocks
    until all complete, so the wait is bounded by the slowest single
    check rather than the sum of every account's check time."""
    if not names:
        return []
    with ThreadPoolExecutor(max_workers=len(names)) as ex:
        return list(ex.map(get_usage, names))

def color(v):
    if v>=80: return RED
    if v>=50: return YELLOW
    return GREEN

def usage():
    d=load()
    names=[a["name"] for a in d["accounts"]]
    if names and not _require_claude():
        return
    if names:
        print(f"Checking {len(names)} account{'s' if len(names)!=1 else ''}...")
    results=get_usage_all(names)
    rows=[]; expired=[]
    for name,u in zip(names,results):
        if not u["active"]:
            expired.append(name)
            continue
        score=u["session"]*0.7+u["week"]*0.3
        rows.append((name,u["session"],u["week"],score))
    rows.sort(key=lambda x:x[3])
    print("\nCLAUDE ACCOUNT USAGE\n")
    print(f"{'Account':12} {'Session':10} {'Weekly':10} Score")
    print("-"*45)
    for n,s,w,sc in rows:
        c=color(s)
        print(f"{n:12} {c}{s:>3}%{RESET}       {c}{w:>3}%{RESET}      {sc:.1f}")
    for n in expired:
        print(f"{n:12} {RED}{'expired':>7}{RESET}    {RED}{'expired':>7}{RESET}    -")
    if rows:
        print(f"\nBest Account: {rows[0][0]}")
    elif expired:
        print("\nAll accounts have expired sessions — run 'claudes' and pick one under \"Login required\" to log back in.")

def _interactive_menu(rows, expired):
    """Keyboard-navigable grid: Up/Down move within a column, Left/Right
    switch column (only when both are present), Enter chooses, q/Ctrl-C
    cancels. `rows` (active, sorted best-first) render under "Available";
    `expired` names render under "Login required" — side by side when both
    are non-empty, otherwise as a single column. Returns ("use", name) for
    a chosen active account, ("login", name) for a chosen login-required
    one, or None if cancelled or raw terminal input isn't available."""
    try:
        import termios, tty
    except ImportError:
        return None

    if not rows and not expired:
        return None
    two_col=bool(rows) and bool(expired)
    col=0 if rows else 1
    row=0

    def plain_row(name,u,sc):
        return f"{name:12} session {u['session']:>3}%  week {u['week']:>3}%  score {sc:5.1f}"

    def colored_row(name,u,sc):
        c=color(u["session"])
        return f"{name:12} session {c}{u['session']:>3}%{RESET}  week {c}{u['week']:>3}%{RESET}  score {sc:5.1f}"

    def plain_login(name):
        return f"{name:12} (Enter to log in)"

    box_w_avail=max((len(plain_row(n,u,sc)) for n,u,sc in rows), default=0)
    box_w_login=max((len(plain_login(n)) for n in expired), default=0)

    def box_lines(plain,colored,width,selected):
        pad=" "*(width-len(plain))
        if selected:
            content=f"\033[7m{plain}{pad}{RESET}"
            bc=GREEN
        else:
            content=colored+pad
            bc=GRAY
        hbar="─"*(width+2)
        return [
            f"{bc}┌{hbar}┐{RESET}",
            f"{bc}│{RESET} {content} {bc}│{RESET}",
            f"{bc}└{hbar}┘{RESET}",
        ]

    GAP="    "

    def render():
        if two_col:
            lines=["Select an account (↑/↓ move, ←/→ switch, Enter choose, q cancel):",""]
        else:
            lines=["Select an account (↑/↓ move, Enter choose, q cancel):",""]

        avail_blocks=[box_lines(plain_row(n,u,sc), colored_row(n,u,sc), box_w_avail, col==0 and row==i)
                      for i,(n,u,sc) in enumerate(rows)]
        login_blocks=[box_lines(plain_login(n), f"{RED}{plain_login(n)}{RESET}", box_w_login, col==1 and row==j)
                      for j,n in enumerate(expired)]

        full_avail=box_w_avail+4
        full_login=box_w_login+4

        if two_col:
            lines.append(f"{'Available:':<{full_avail}}{GAP}Login required:")
            for i in range(max(len(avail_blocks), len(login_blocks))):
                a=avail_blocks[i] if i<len(avail_blocks) else [" "*full_avail]*3
                b=login_blocks[i] if i<len(login_blocks) else [" "*full_login]*3
                for la,lb in zip(a,b):
                    lines.append(la+GAP+lb)
        elif rows:
            lines.append("Available:")
            for b in avail_blocks: lines+=b
        else:
            lines.append("Login required:")
            for b in login_blocks: lines+=b
        return lines

    fd=sys.stdin.fileno()
    old=termios.tcgetattr(fd)
    lines=render()
    print("\n".join(lines))
    result=None
    try:
        tty.setraw(fd)
        while True:
            ch=sys.stdin.read(1)
            key=None
            if ch=="\x1b":
                if sys.stdin.read(1)=="[":
                    key={"A":"up","B":"down","C":"right","D":"left"}.get(sys.stdin.read(1))
            elif ch in ("\r","\n"):
                key="enter"
            elif ch in ("\x03","q","Q"):
                key="cancel"

            if key=="enter":
                name=rows[row][0] if col==0 else expired[row]
                result=("use" if col==0 else "login", name)
                break
            if key=="cancel":
                result=None
                break
            moved=False
            if key in ("up","down"):
                n=len(rows) if col==0 else len(expired)
                row=(row-1)%n if key=="up" else (row+1)%n
                moved=True
            elif key in ("left","right") and two_col:
                col=1-col
                other_n=len(rows) if col==0 else len(expired)
                row=min(row, other_n-1)
                moved=True
            if moved:
                sys.stdout.write(f"\033[{len(lines)}A\r")
                lines=render()
                for l in lines:
                    sys.stdout.write("\033[2K"+l+"\r\n")
                sys.stdout.flush()
    except KeyboardInterrupt:
        result=None
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return result

def _choose_account():
    """Check every account's session and usage concurrently (bounded by
    the slowest single check, not the sum of all), then offer an
    arrow-key menu: active accounts under "Available" (best score
    first), expired ones under "Login required" — picking one of those
    launches claude so you can log back in, then re-checks everything.
    Returns the chosen account name."""
    d=load()
    accounts=d["accounts"]
    if not accounts:
        print("No accounts")
        return None

    if not _require_claude():
        return None

    names=[a["name"] for a in accounts]
    print(f"Checking {len(names)} account{'s' if len(names)!=1 else ''}...")
    results=get_usage_all(names)

    rows=[]
    expired=[]
    for name,u in zip(names,results):
        if not u["active"]:
            print(f"  {RED}✗ {name:12} session expired{RESET}")
            expired.append(name)
            continue
        sc=u["session"]*0.7+u["week"]*0.3
        rows.append((name,u,sc))
        c=color(u["session"])
        print(f"  {GREEN}✓{RESET} {name:12} session {c}{u['session']:>3}%{RESET}  week {c}{u['week']:>3}%{RESET}  score {sc:5.1f}")

    rows.sort(key=lambda r: r[2])
    print()

    if rows:
        print(f"Recommended: {rows[0][0]} — lowest score {rows[0][2]:.1f} among active sessions (70% session + 30% weekly usage)\n")
        if not sys.stdin.isatty():
            return rows[0][0]
    else:
        msg="No accounts with an active session."
        if expired:
            msg+=f" ({', '.join(expired)} need a fresh login.)"
        print(msg)
        if not sys.stdin.isatty() or not expired:
            return None

    choice=_interactive_menu(rows, expired)
    if choice is None:
        return None
    kind,name=choice
    if kind=="use":
        return name
    _login(name)
    return _choose_account()

def migrate():
    """Set up shared session layer and import all historical data."""
    ensure()
    print("Setting up shared session layer...\n")

    d = load()
    registered_paths = {config_dir(a) for a in d["accounts"] if "config_path" in a or "path" in a}

    for a in d["accounts"]:
        try:
            cp = config_dir(a)
        except KeyError:
            continue
        if _has_active_sessions(cp):
            print(f"  Skipping {a['name']} — Claude is currently running under this profile.")
            print(f"    Close all Claude sessions for '{a['name']}' and re-run 'claudes migrate'.")
            continue
        print(f"  Linking {a['name']} ({cp})...")
        setup_shared_links(cp)

    # Fold the default `claude` config (used when CLAUDE_CONFIG_DIR isn't set)
    # into the shared layer too, so plain `claude` stays in sync with every
    # pool account from now on — not just a one-time snapshot.
    default_claude = HOME / ".claude"
    if str(default_claude) not in registered_paths and default_claude.is_dir():
        if _has_active_sessions(default_claude):
            print("  Skipping ~/.claude — Claude is currently running under it.")
            print("    Close that Claude session and re-run 'claudes migrate'.")
        else:
            print("  Linking ~/.claude (default config)...")
            setup_shared_links(default_claude)

    print("\nImporting remaining historical session data...")
    names = [a["name"] for a in d["accounts"]]
    sources = []

    # Old per-name dirs directly under ~/.claudes/ (stale from earlier setup)
    claudes_default = HOME / ".claudes"
    for name in names:
        p = claudes_default / name
        if p.is_dir() and not p.is_symlink() and str(p) not in registered_paths:
            sources.append(p)

    # Stale per-account sub-dirs left under ~/.claude from earlier setups
    # (~/.claude itself is handled above via setup_shared_links, not here)
    for name in names:
        for sub in [default_claude / name, default_claude / "profiles" / name]:
            if sub.is_dir() and not sub.is_symlink() and str(sub) not in registered_paths:
                sources.append(sub)

    total_s = total_h = 0
    for src in sources:
        ns = _merge_projects(src / "projects", SHARED / "projects", move=False)
        nh = _merge_history(src / "history.jsonl", SHARED / "history.jsonl")
        if ns or nh:
            print(f"  {src}: {ns} sessions, {nh} history entries")
        total_s += ns
        total_h += nh

    print(f"\nDone. {total_s} session files imported, {total_h} history entries merged.")
    print(f"Shared layer: {SHARED}")


if __name__=="__main__":
    cmd=sys.argv[1] if len(sys.argv)>1 else ""
    if cmd=="install": install()
    elif cmd=="add": add(sys.argv[2])
    elif cmd=="list": list_accounts()
    elif cmd=="usage": usage()
    elif cmd=="migrate": migrate()
    elif cmd=="":
        acc=_choose_account()
        if acc: launch(acc)
    elif find(cmd):
        launch(cmd)
    else:
        print("Commands: install, add <name>, list, usage, migrate")
        print("Run 'claudes' with no arguments to pick an account and launch it.")
        print("Run 'claudes <name>' to launch a specific account directly.")
        names=sorted(a["name"] for a in load()["accounts"])
        if names:
            print(f"Configured accounts: {', '.join(names)}")
