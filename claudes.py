#!/usr/bin/env python3
import json, os, re, shutil, stat, subprocess, sys
from pathlib import Path

HOME = Path.home()
BASE = Path(os.environ.get("CLAUDES_BASE", HOME / ".claudes")).expanduser()
PROFILES = BASE / "profiles"
ACCOUNTS = BASE / "accounts.json"
CURRENT = BASE / "current_profile"
SHARED = BASE / "shared"

GREEN="\033[92m"; YELLOW="\033[93m"; RED="\033[91m"; RESET="\033[0m"

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
    print("Launching claude to log in...")
    launch(name)

def list_accounts():
    d=load()
    for a in sorted(d["accounts"], key=lambda x:x["name"]):
        print(a["name"])

def launch(name):
    a=find(name)
    if not a:
        print("Not found"); return
    CURRENT.write_text(name)
    _sync_last_session(name)
    env=os.environ.copy()
    env["CLAUDE_CONFIG_DIR"]=config_dir(a)
    sys.stdout.flush()
    subprocess.run(["claude"], env=env)

def get_usage(name):
    a=find(name)
    if not a: return None
    env=os.environ.copy()
    env["CLAUDE_CONFIG_DIR"]=config_dir(a)
    try:
        r=subprocess.run(["claude","-p","/usage"],capture_output=True,text=True,env=env,timeout=60)
        out=r.stdout
        s=re.search(r"Current session:\s+(\d+)%", out)
        w=re.search(r"Current week.*?:\s+(\d+)%", out)
        return {
            "session": int(s.group(1)) if s else 0,
            "week": int(w.group(1)) if w else 0
        }
    except Exception:
        return {"session":0,"week":0}

def color(v):
    if v>=80: return RED
    if v>=50: return YELLOW
    return GREEN

def usage():
    d=load()
    rows=[]
    for a in d["accounts"]:
        u=get_usage(a["name"])
        score=u["session"]*0.7+u["week"]*0.3
        rows.append((a["name"],u["session"],u["week"],score))
    rows.sort(key=lambda x:x[3])
    print("\nCLAUDE ACCOUNT USAGE\n")
    print(f"{'Account':12} {'Session':10} {'Weekly':10} Score")
    print("-"*45)
    for n,s,w,sc in rows:
        c=color(s)
        print(f"{n:12} {c}{s:>3}%{RESET}       {c}{w:>3}%{RESET}      {sc:.1f}")
    if rows:
        print(f"\nBest Account: {rows[0][0]}")

def _pick_best():
    """Show a live usage log for every account, recommend the lowest-scoring
    one, and let the user accept it or pick another. Returns the chosen name."""
    d=load()
    accounts=d["accounts"]
    if not accounts:
        print("No accounts")
        return None

    print("Checking account usage...\n")
    rows=[]
    best_idx=None; best_score=None
    for a in accounts:
        u=get_usage(a["name"])
        sc=u["session"]*0.7+u["week"]*0.3
        rows.append((a["name"],u,sc))
        if best_score is None or sc<best_score:
            best_score=sc; best_idx=len(rows)-1

    for i,(name,u,sc) in enumerate(rows):
        c=color(u["session"])
        tag="  <- recommended" if i==best_idx else ""
        print(f"  {i+1}. {name:12} session {c}{u['session']:>3}%{RESET}  week {c}{u['week']:>3}%{RESET}  score {sc:5.1f}{tag}")

    best_name=rows[best_idx][0]
    print(f"\nRecommended: {best_name} — lowest score {best_score:.1f} (70% session + 30% weekly usage)")

    if not sys.stdin.isatty():
        return best_name

    try:
        raw=input(f"Use {best_name}? [Enter to accept, or enter a number 1-{len(rows)}]: ").strip()
    except EOFError:
        raw=""
    if raw.isdigit() and 1<=int(raw)<=len(rows):
        return rows[int(raw)-1][0]
    return best_name

def best():
    acc=_pick_best()
    if acc:
        print(acc)

def switch_best():
    acc=_pick_best()
    if acc:
        launch(acc)

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


cmd=sys.argv[1] if len(sys.argv)>1 else ""
if cmd=="install": install()
elif cmd=="add": add(sys.argv[2])
elif cmd=="list": list_accounts()
elif cmd in ("launch", "switch"): launch(sys.argv[2])
elif cmd=="usage": usage()
elif cmd=="best": best()
elif cmd=="switch-best": switch_best()
elif cmd=="migrate": migrate()
else:
    print("Commands: install, add <name>, list, launch|switch <name>, usage, best, switch-best, migrate")
