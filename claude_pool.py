import os
import shutil
import stat
from pathlib import Path


def install():
    home = Path.home()

    base_dir = home / ".claudes"
    profiles_dir = base_dir / "profiles"
    logs_dir = base_dir / "logs"
    accounts_file = base_dir / "accounts.json"

    profiles_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    if not accounts_file.exists():
        accounts_file.write_text('{"accounts": []}')

    current_script = Path(__file__).resolve().with_name("claudes.py")

    installed_script = base_dir / "claudes"

    shutil.copy2(current_script, installed_script)

    installed_script.chmod(
        installed_script.stat().st_mode | stat.S_IEXEC
    )

    link_locations = [
        Path("/usr/local/bin/claudes"),
        home / "bin" / "claudes",
    ]

    link_created = False

    for link in link_locations:
        try:
            link.parent.mkdir(parents=True, exist_ok=True)

            if link.exists() or link.is_symlink():
                link.unlink()

            link.symlink_to(installed_script)

            print(f"✓ Command installed: {link}")
            link_created = True
            break

        except Exception:
            pass

    if not link_created:
        print()
        print("Could not create system symlink.")
        print("Add this manually to ~/.zshrc:")
        print()
        print('export PATH="$HOME/.claudes:$PATH"')
        print()

    zshrc = home / ".zshrc"

    path_line = 'export PATH="$HOME/.claudes:$PATH"'

    try:
        existing = zshrc.read_text() if zshrc.exists() else ""

        if path_line not in existing:
            with open(zshrc, "a") as f:
                f.write("\n" + path_line + "\n")

            print("✓ Added ~/.claudes to PATH")
    except Exception:
        pass

    print()
    print("Installation complete")
    print()
    print(f"Base Directory : {base_dir}")
    print(f"Profiles       : {profiles_dir}")
    print(f"Accounts File  : {accounts_file}")
    print()
    print("Restart terminal and run:")
    print()
    print("    claudes list")
    print()
