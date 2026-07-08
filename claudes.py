#!/usr/bin/env python3
import json, os, re, shutil, stat, subprocess, sys
from pathlib import Path

HOME = Path.home()
BASE = Path(os.environ.get("CLAUDES_BASE", HOME / ".claudes")).expanduser()
PROFILES = BASE / "profiles"
ACCOUNTS = BASE / "accounts.json"
CURRENT = BASE / "current_profile"

GREEN="\033[92m"; YELLOW="\033[93m"; RED="\033[91m"; RESET="\033[0m"

def ensure():
    BASE.mkdir(exist_ok=True)
    PROFILES.mkdir(exist_ok=True)
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
    env=os.environ.copy()
    env["CLAUDE_CONFIG_DIR"]=config_dir(a)
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

def best():
    d=load()
    best_acc=None; best_score=9999
    for a in d["accounts"]:
        u=get_usage(a["name"])
        sc=u["session"]*0.7+u["week"]*0.3
        if sc<best_score:
            best_score=sc; best_acc=a["name"]
    print(best_acc or "No accounts")

def switch_best():
    d=load()
    best_acc=None; best_score=9999
    for a in d["accounts"]:
        u=get_usage(a["name"])
        sc=u["session"]*0.7+u["week"]*0.3
        if sc<best_score:
            best_score=sc; best_acc=a["name"]
    if best_acc:
        launch(best_acc)

cmd=sys.argv[1] if len(sys.argv)>1 else ""
if cmd=="install": install()
elif cmd=="add": add(sys.argv[2])
elif cmd=="list": list_accounts()
elif cmd in ("launch", "switch"): launch(sys.argv[2])
elif cmd=="usage": usage()
elif cmd=="best": best()
elif cmd=="switch-best": switch_best()
else:
    print("Commands: install, add <name>, list, launch|switch <name>, usage, best, switch-best")
