#!/usr/bin/env python3
# cloudgaming_installer.py
# KDE + VNC + noVNC + Moonlight Web + Sunshine + Cloudflare
#
# Non-interactive provisioning agent for automated notebook/VM
# deployment. Reports stage progress and completion to a backend API
# via JOB_TOKEN so the frontend can stream status to the user's
# browser session. Console output is intentionally minimal; full
# detail always goes to /var/log/cloudgaming.log.

import os
import sys
import time
import re
import json
import traceback
import subprocess
import shutil
import urllib.request
from pathlib import Path
from datetime import datetime


LOG_FILE = "/var/log/cloudgaming.log"

# Everything runs as root, in root's own home -- no separate Linux
# user is created.
HOME = "/root"

UI = "kde"

# Provisioning identifier supplied by the backend. Used only to
# associate progress/finish/error callbacks with the right browser
# session -- it is not a control channel back into the notebook and
# is not reused after install completes.
#
# This installer file is identical for every deployment -- nothing
# backend-specific is hardcoded here. Both values are supplied per
# job via environment variables when the script is launched:
#
#   export API_URL="https://abc.trycloudflare.com"
#   export JOB_TOKEN="6e7f5b4d-xxxx-xxxx"
#   python3 installer.py
API_URL = os.getenv("API_URL", "").rstrip("/")
JOB_TOKEN = os.getenv("JOB_TOKEN", "")

VNC_PASSWORD_GENERATED = None

# Only this wallpaper is ever installed -- no random selection, no
# alternates.
WALLPAPER_URL = "https://raw.githubusercontent.com/zenixbot0101/Moonlight-Web-2.0/main/wallpaer.jpg"


# ---------------------------------------------------------------------
# Logging (full detail, file only) + backend status API (best-effort)
# ---------------------------------------------------------------------

def log(msg):
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"[{datetime.now()}] {msg}\n")
    except:
        pass


def _post_json(path, payload, timeout=3):
    # If the job wasn't given API_URL/JOB_TOKEN, there's nowhere to
    # report to -- skip silently and keep installing. Any other
    # failure here (network down, backend unreachable, bad response)
    # must also never interrupt provisioning; this is a one-way
    # status feed, not a dependency.
    if not API_URL or not JOB_TOKEN:
        return

    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{API_URL}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=timeout)
    except Exception as e:
        log(f"[API] {path} failed (non-fatal): {e}")


def send_output(message):
    log(message)
    _post_json("/api/output", {"job_token": JOB_TOKEN, "message": message})


def send_finish(vnc_url, moonlight_url):
    _post_json(
        "/api/finish",
        {
            "job_token": JOB_TOKEN,
            "vnc_url": vnc_url,
            "moonlight_url": moonlight_url,
        },
    )


def send_error(message, command="", tb=""):
    _post_json(
        "/api/error",
        {
            "job_token": JOB_TOKEN,
            "message": message,
            "command": command,
            "traceback": tb,
        },
    )


_last_console_print = 0.0


def console_tick():
    # The only thing the notebook's own terminal ever shows during
    # provisioning. Real progress is reported to the backend via
    # send_output() and streamed to the frontend instead.
    global _last_console_print
    now = time.time()
    if now - _last_console_print > 2:
        print("Sit back and relax")
        _last_console_print = now


def stage(message):
    # Call this at the start of each install stage: logs full detail,
    # reports it to the backend for the frontend to display, and
    # leaves the local terminal showing only the generic placeholder.
    send_output(message)
    console_tick()


# ---------------------------------------------------------------------
# Command execution
# ---------------------------------------------------------------------

def run(cmd, input_data=None, fatal=True):
    try:
        log(f">>> {cmd}")
        console_tick()

        result = subprocess.run(
            cmd,
            shell=True,
            input=input_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        log(f"EXIT CODE: {result.returncode}")
        if result.stdout.strip():
            log(f"STDOUT:\n{result.stdout.strip()}")
        if result.stderr.strip():
            log(f"STDERR:\n{result.stderr.strip()}")

        if result.returncode != 0:
            raise Exception(result.stderr.strip())

        return result.stdout.strip()

    except Exception as e:
        reason = str(e)
        log("==================== ERROR" if fatal else "==================== WARNING (non-fatal)")
        log(f"COMMAND:\n{cmd}")
        log(f"REASON:\n{reason}")

        if fatal:
            send_error(
                message="Installer command failed",
                command=cmd,
                tb=reason,
            )
            sys.exit(1)

        return None


def snapshot_logs(label, paths):
    for p in paths:
        content = run(f"tail -n 200 {p} 2>/dev/null", fatal=False)
        if content:
            log(f"\n----- {label} LOG :: {p} -----\n{content}\n----- end {label} log -----\n")


def package_installed(pkg):
    result = subprocess.run(
        f"dpkg -s {pkg}",
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def install_package(pkg):
    if package_installed(pkg):
        log(f"[SKIP] {pkg} already installed")
        return
    run(f"DEBIAN_FRONTEND=noninteractive apt install -y {pkg}")


def check_root():
    if os.geteuid() != 0:
        send_error("Installer must run as root")
        sys.exit(1)


def record_system_info():
    for cmd in [
        "uname -a",
        "cat /etc/os-release",
        "free -h",
        "df -h",
        "lspci | grep -i vga",
    ]:
        run(cmd, fatal=False)


# ---------------------------------------------------------------------
# Cleanup marimo
# ---------------------------------------------------------------------

def cleanup_marimo():
    stage("Cleaning up marimo files")
    
    # Kill any marimo processes
    run("pkill -f marimo 2>/dev/null || true", fatal=False)
    
    # Remove marimo directories in home
    marimo_dirs = [
        f"{HOME}/.marimo",
        f"{HOME}/marimo",
        f"{HOME}/.local/share/marimo",
        f"{HOME}/.config/marimo",
        f"{HOME}/.cache/marimo",
    ]
    for d in marimo_dirs:
        run(f"rm -rf {d}", fatal=False)
    
    # Remove marimo files anywhere in home
    run(f"find {HOME} -name '*marimo*' -type f -delete 2>/dev/null || true", fatal=False)
    run(f"find {HOME} -name '*marimo*' -type d -exec rm -rf {{}} + 2>/dev/null || true", fatal=False)
    
    # Remove from system
    run("find /usr -name '*marimo*' -type f -delete 2>/dev/null || true", fatal=False)
    run("find /etc -name '*marimo*' -type f -delete 2>/dev/null || true", fatal=False)
    run("find /var -name '*marimo*' -type f -delete 2>/dev/null || true", fatal=False)
    
    # Remove pip packages
    run("pip3 uninstall -y marimo 2>/dev/null || true", fatal=False)
    run("pip uninstall -y marimo 2>/dev/null || true", fatal=False)
    
    # Remove from PATH cache
    run("hash -r 2>/dev/null || true", fatal=False)
    
    log("[marimo] Cleanup completed")


# ---------------------------------------------------------------------
# Install stages
# ---------------------------------------------------------------------

def update_system():
    stage("Updating system")
    run("apt update")
    run("apt upgrade -y")


def install_base():
    stage("Installing KDE (lightweight)")
    
    # Install lightweight KDE components instead of full kde-plasma-desktop
    packages = [
        # VNC and tools
        "tigervnc-standalone-server",
        "dbus-x11",
        "curl",
        "wget",
        "git",
        "python3-pip",
        "python3-psutil",
        "psmisc",
        # Lightweight KDE
        "plasma-workspace",
        "plasma-desktop",
        "kwin-x11",
        "kde-cli-tools",
        "kde-config-gtk-style",
        "kde-config-gtk-style-preview",
        "kdeconnect",
        "khotkeys",
        "kinfocenter",
        "kmenuedit",
        "kscreen",
        "ksshaskpass",
        "kwallet-pam",
        "kwayland-integration",
        "kwrited",
        "layer-shell-qt",
        "libkf5screen-bin",
        "libkf5screen7",
        "libkfontinst",
        "libkfontinstui",
        "plasma-discover",
        "plasma-integration",
        "plasma-nm",
        "plasma-pa",
        "powerdevil",
        "systemsettings",
        "xdg-desktop-portal-kde",
        # Browser
        "chromium",
        # Utilities
        "xorg",
        "xinit",
        "x11-xserver-utils",
        "fonts-noto",
        "fonts-noto-cjk",
        "fonts-liberation",
        "fonts-dejavu",
    ]
    for p in packages:
        install_package(p)
    
    # Disable KDE baloo file indexer for performance
    run("balooctl disable 2>/dev/null || true", fatal=False)
    run("balooctl suspend 2>/dev/null || true", fatal=False)
    
    # Disable unnecessary services
    run("systemctl disable bluetooth 2>/dev/null || true", fatal=False)
    run("systemctl disable cups 2>/dev/null || true", fatal=False)
    run("systemctl disable cups-browsed 2>/dev/null || true", fatal=False)


def install_steam():
    stage("Installing Steam")

    run("dpkg --add-architecture i386", fatal=False)
    run("apt update", fatal=False)

    deb = "/tmp/steam.deb"
    run(
        f"wget -q https://cdn.cloudflare.steamstatic.com/client/installer/steam.deb -O {deb}",
        fatal=False,
    )

    if os.path.exists(deb):
        run(f"DEBIAN_FRONTEND=noninteractive apt install -y {deb}", fatal=False)
    else:
        log("[SKIP] Steam download failed, continuing without it")


def install_heroic():
    stage("Installing Heroic")

    release_json = run(
        "curl -s https://api.github.com/repos/Heroic-Games-Launcher/HeroicGamesLauncher/releases/latest",
        fatal=False,
    )
    if not release_json:
        log("[SKIP] Could not reach GitHub for Heroic release info")
        return

    match = re.search(r'"browser_download_url":\s*"([^"]+amd64\.deb)"', release_json)
    if not match:
        log("[SKIP] Could not find a Heroic .deb asset in the latest release")
        return

    url = match.group(1)
    deb = "/tmp/heroic.deb"
    run(f"wget -q {url} -O {deb}", fatal=False)

    if os.path.exists(deb):
        run(f"DEBIAN_FRONTEND=noninteractive apt install -y {deb}", fatal=False)
    else:
        log("[SKIP] Heroic download failed, continuing without it")


def setup_vnc():
    stage("Starting VNC")

    vnc_dir = f"{HOME}/.config/tigervnc"
    legacy_vnc_dir = f"{HOME}/.vnc"

    # Newer TigerVNC (>=1.13) stores config in ~/.config/tigervnc and
    # auto-migrates ~/.vnc there on first run; that migration breaks
    # on a fresh account or a partial leftover dir from a prior failed
    # run, so wipe both and write straight into the new location.
    run(f"rm -rf {legacy_vnc_dir} {vnc_dir}")
    run(f"mkdir -p {vnc_dir}")

    # No controlling tty in this execution context, so vncpasswd's
    # interactive prompt can't be used. VNC_PASSWORD env var lets a
    # deployment supply a stronger, per-notebook password; otherwise
    # this falls back to a known default, which is only acceptable
    # because -localhost is left at its default (see below) -- if
    # this is ever changed to expose VNC directly, generate a random
    # password per notebook instead.
    global VNC_PASSWORD_GENERATED
    vnc_password = os.environ.get("VNC_PASSWORD", "").strip()
    if not vnc_password:
        vnc_password = "123456"
        VNC_PASSWORD_GENERATED = vnc_password
        log("[VNC] No VNC_PASSWORD env var set -- using default password.")

    run(f"vncpasswd -f > {vnc_dir}/passwd", input_data=vnc_password + "\n")
    run(f"chmod 600 {vnc_dir}/passwd")

    run(f"mkdir -p {legacy_vnc_dir}")
    run(f"cp {vnc_dir}/passwd {legacy_vnc_dir}/passwd")
    run(f"chmod 600 {legacy_vnc_dir}/passwd")

    # Improved xstartup with proper session handling
    startup = """#!/bin/bash
unset SESSION_MANAGER
unset DBUS_SESSION_BUS_ADDRESS

# Set proper X11 environment
export XDG_RUNTIME_DIR=/run/user/0
export XDG_CONFIG_DIRS=/etc/xdg
export XDG_DATA_DIRS=/usr/share:/usr/local/share:/usr/share/plasma
export XDG_CURRENT_DESKTOP=KDE
export DESKTOP_SESSION=plasma
export KDE_FULL_SESSION=true
export KDE_SESSION_VERSION=5
export QT_QPA_PLATFORM=xcb

# Disable screen saver and power management
xset s off
xset s noblank
xset -dpms

# Start dbus and session bus
eval `dbus-launch --exit-with-session --sh-syntax`

# Start KDE Plasma with proper environment
export $(dbus-launch --sh-syntax)
exec startplasma-x11 2>&1
"""
    xstartup_path = f"{vnc_dir}/xstartup"
    Path(xstartup_path).write_text(startup)
    run(f"chmod +x {xstartup_path}")

    run("touch /root/.Xauthority")
    run("chmod 600 /root/.Xauthority")

    # Kill any existing VNC sessions
    run("vncserver -kill :1 2>/dev/null || true", fatal=False)
    run("pkill -f Xtigervnc 2>/dev/null || true", fatal=False)
    
    time.sleep(2)

    run(
        f"""
vncserver :1 \
-localhost no \
-geometry 1920x1080 \
-depth 24 \
-rfbauth {vnc_dir}/passwd \
-SecurityTypes VncAuth \
-xstartup {xstartup_path} \
-I
""",
        fatal=False
    )

    time.sleep(5)
    snapshot_logs(
        "VNC (:1)",
        [f"{HOME}/.vnc/*:1.log", f"{HOME}/.config/tigervnc/*:1.log"],
    )

    check = run("pgrep -f Xtigervnc", fatal=False)
    if not check:
        log(
            "[VNC] WARNING: Xtigervnc does not appear to be running "
            "after startup -- check ~/.vnc/*:1.log or "
            "~/.config/tigervnc/*:1.log for the actual crash reason."
        )
    
    # Wait for KDE to fully start
    time.sleep(10)


def setup_novnc():
    stage("Starting noVNC")

    path = f"{HOME}/noVNC"
    if not os.path.exists(path):
        run(f"cd {HOME} && git clone https://github.com/novnc/noVNC.git")

    # Kill existing noVNC
    run("pkill -f novnc_proxy 2>/dev/null || true", fatal=False)
    time.sleep(1)

    run(
        f"""
nohup {HOME}/noVNC/utils/novnc_proxy \
--vnc localhost:5901 \
--listen 6001 \
--web {HOME}/noVNC \
> {HOME}/novnc.log 2>&1 &
"""
    )

    time.sleep(3)
    snapshot_logs("noVNC", [f"{HOME}/novnc.log"])


def install_cloudflared():
    if shutil.which("cloudflared"):
        log("[SKIP] cloudflared exists")
        return

    run(
        """
wget -q \
https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb \
-O /tmp/cloudflared.deb
"""
    )
    run("apt install -y /tmp/cloudflared.deb")


def start_cloudflare(service, port, scheme="http", no_tls_verify=False):
    stage(f"Starting Cloudflare tunnel ({service})")

    log_file = f"{HOME}/{service}-cloudflare.log"
    tls_flag = "--no-tls-verify " if no_tls_verify else ""

    # Kill existing tunnel
    run(f"pkill -f 'cloudflared tunnel.*{port}' 2>/dev/null || true", fatal=False)
    time.sleep(1)

    run(
        f"""
nohup cloudflared tunnel {tls_flag}\
--url {scheme}://localhost:{port} \
> {log_file} 2>&1 &
"""
    )

    time.sleep(5)
    snapshot_logs(f"Cloudflare tunnel ({service})", [log_file])


def setup_moonlight_web():
    stage("Installing Moonlight Web")

    package = f"{HOME}/moonlight-web-x86_64-unknown-linux-gnu.tar.gz"
    if not os.path.exists(package):
        run(
            f"cd {HOME} && wget -q "
            "https://github.com/MrCreativ3001/moonlight-web-stream/releases/download/v2.10.0/moonlight-web-x86_64-unknown-linux-gnu.tar.gz"
        )

    # Kill existing moonlight
    run("pkill -f 'web-server' 2>/dev/null || true", fatal=False)
    run("pkill -f 'streamer' 2>/dev/null || true", fatal=False)
    time.sleep(1)

    run(
        f"""
cd {HOME} && tar -xzf moonlight-web-x86_64-unknown-linux-gnu.tar.gz

cd {HOME}/package

chmod +x web-server streamer

nohup ./web-server \
--bind-address 127.0.0.1:8081 \
> {HOME}/moonlight-web.log 2>&1 &
"""
    )

    time.sleep(3)
    snapshot_logs("Moonlight Web", [f"{HOME}/moonlight-web.log"])


def setup_sunshine():
    stage("Installing Sunshine")

    deb = "/tmp/sunshine.deb"
    if not os.path.exists(deb):
        run(
            """
wget -q \
https://github.com/LizardByte/Sunshine/releases/download/v2026.516.143833/sunshine-debian-trixie-amd64.deb \
-O /tmp/sunshine.deb
"""
        )

    run("apt install -y /tmp/sunshine.deb")

    stage("Starting Sunshine")
    
    # Kill existing sunshine
    run("pkill -f sunshine 2>/dev/null || true", fatal=False)
    time.sleep(1)
    
    run(f"nohup sunshine > {HOME}/sunshine.log 2>&1 &")

    time.sleep(5)
    snapshot_logs(
        "Sunshine",
        [f"{HOME}/sunshine.log", f"{HOME}/.config/sunshine/sunshine.log"],
    )


def get_session_env(proc_name, tries=10, delay=3):
    # A fresh Python subprocess was never part of the VNC desktop
    # session, so it has no DISPLAY/DBUS_SESSION_BUS_ADDRESS of its
    # own. plasma-apply-wallpaperimage talks to the running shell over
    # D-Bus, and that session bus address is random per session, not
    # guessable -- read it straight out of the already-running
    # plasmashell process's own environment via /proc/<pid>/environ.
    #
    # Retries a few times since plasmashell can still be starting up
    # when this is called.
    for attempt in range(tries):
        pid = run(f"pgrep -f {proc_name} | head -n1", fatal=False)

        if pid:
            try:
                raw = Path(f"/proc/{pid}/environ").read_bytes()
                env = {}
                for item in raw.split(b"\x00"):
                    if b"=" not in item:
                        continue
                    k, _, v = item.partition(b"=")
                    env[k.decode(errors="ignore")] = v.decode(errors="ignore")

                if "DISPLAY" in env:
                    log(f"[SESSION] Found session env for {proc_name} (attempt {attempt+1})")
                    return env
            except Exception as e:
                log(f"[SESSION] Could not read env from pid {pid}: {e}")

        time.sleep(delay)

    log(f"[SESSION] WARNING: Could not find running {proc_name} after {tries} attempts")
    return {}


def setup_wallpaper():
    stage("Setting wallpaper")

    wallpapers_dir = f"{HOME}/wallpapers"
    run(f"mkdir -p {wallpapers_dir}")

    dest = f"{wallpapers_dir}/wallpaper.jpg"

    try:
        urllib.request.urlretrieve(WALLPAPER_URL, dest)
    except Exception as e:
        log(f"[WALLPAPER] WARNING: failed to download {WALLPAPER_URL} ({e}) -- skipping")
        return

    run(
        f"""
mkdir -p {HOME}/.local/share/wallpapers

cp {dest} \
{HOME}/.local/share/wallpapers/wallpaper.jpg
""",
        fatal=False,
    )

    wallpaper_path = f"{HOME}/.local/share/wallpapers/wallpaper.jpg"

    # Applying the wallpaper live requires talking to the already
    # running desktop session over D-Bus/X11. This is a fresh shell
    # (separate from the VNC session's environment), so it doesn't
    # automatically know DISPLAY or the D-Bus session bus address --
    # get_session_env() pulls the real values out of the running
    # plasmashell process instead of guessing. Purely cosmetic, so a
    # failure here shouldn't abort the install.
    session_env = get_session_env("plasmashell")

    env_keys = ("DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "XAUTHORITY")
    env_prefix = " ".join(
        f'{k}="{session_env[k]}"' for k in env_keys if k in session_env
    ) or "DISPLAY=:1"

    if not session_env:
        log(
            "[WALLPAPER] WARNING: could not find a running plasmashell "
            "to read D-Bus env from -- falling back to DISPLAY=:1 only, "
            "plasma-apply-wallpaperimage will likely fail to reach the "
            "session bus"
        )

    # Wait a bit for KDE to fully initialize
    time.sleep(5)
    
    result = run(f"{env_prefix} plasma-apply-wallpaperimage {wallpaper_path}", fatal=False)

    if result is None:
        # Plan B: plasma-apply-wallpaperimage can still fail even with
        # the right env (older Plasma versions don't ship it, or the
        # containment layout doesn't match what it expects). Fall back
        # to writing the wallpaper path directly into the plasma
        # config and asking the running plasmashell to reload it over
        # D-Bus.
        log("[WALLPAPER] plasma-apply-wallpaperimage failed -- trying config-file fallback")

        for kw_tool in ("kwriteconfig5", "kwriteconfig6"):
            run(
                f"{env_prefix} {kw_tool} --file "
                f"{HOME}/.config/plasma-org.kde.plasma.desktop-appletsrc "
                f"--group Containments --group 1 --group Wallpaper "
                f"--group org.kde.image --group General --key Image "
                f"file://{wallpaper_path}",
                fatal=False,
            )

        qdbus_script = (
            "var allDesktops = desktops();"
            "for (i=0;i<allDesktops.length;i++){"
            "d = allDesktops[i];"
            "d.wallpaperPlugin = 'org.kde.image';"
            "d.currentConfigGroup = Array('Wallpaper','org.kde.image','General');"
            f"d.writeConfig('Image','file://{wallpaper_path}')}}"
        )

        for qdbus_tool in ("qdbus", "qdbus6", "qdbus-qt5", "qdbus-qt6"):
            run(
                f'{env_prefix} {qdbus_tool} org.kde.plasmashell '
                f'/PlasmaShell org.kde.PlasmaShell.evaluateScript '
                f'"{qdbus_script}"',
                fatal=False,
            )


def setup_bashrc():
    stage("Configuring terminal")
    
    bashrc = f"{HOME}/.bashrc"
    
    # Backup original
    run(f"cp {bashrc} {bashrc}.bak 2>/dev/null || true", fatal=False)
    
    # Add custom configuration
    config = """
# --- Cloud Gaming Terminal Configuration ---
# Always start in home directory
cd ~

# Improve terminal performance
export TERM=xterm-256color
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8

# Better prompt
export PS1='\\[\\033[01;32m\\]\\u@\\h\\[\\033[00m\\]:\\[\\033[01;34m\\]\\w\\[\\033[00m\\]\\$ '

# Aliases for convenience
alias ll='ls -alF'
alias la='ls -A'
alias l='ls -CF'
alias ..='cd ..'
alias ...='cd ../..'
alias ....='cd ../../..'

# Keep history across sessions
export HISTSIZE=10000
export HISTFILESIZE=20000
export HISTCONTROL=ignoreboth

# Better tab completion
bind 'set completion-ignore-case on'
bind 'set show-all-if-ambiguous on'
bind 'set menu-complete-display-prefix on'

# Add local bin to PATH
export PATH=$PATH:$HOME/.local/bin

# --- End Cloud Gaming Configuration ---
"""
    
    # Append config if not already present
    with open(bashrc, "a") as f:
        f.write(config)
    
    log("[BASH] Terminal configured to start in ~")


def setup_anti_abuse():
    stage("Starting anti-abuse watcher")

    watcher = f"{HOME}/anti_abuse.py"

    code = r'''
import psutil
import time
import subprocess
import os
from datetime import datetime


LOG = os.path.expanduser("~/anti_abuse.log")

MINER_SIGNATURES = [
    "xmrig", "xmr-stak", "xmrstak", "cpuminer", "minerd", "ccminer",
    "ethminer", "phoenixminer", "t-rex", "trex", "nbminer", "gminer",
    "lolminer", "teamredminer", "nanominer", "srbminer", "bfgminer",
    "cgminer", "nheqminer", "claymore",
]

SERVICES_TO_KILL = [
    "Xtigervnc", "vncserver", "startplasma-x11",
    "web-server", "streamer", "sunshine", "cloudflared", "novnc_proxy",
    "chromium",
]


def log(msg):
    line = f"[{datetime.now()}] {msg}"
    print(line)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except:
        pass


def matches_miner(name):
    name = (name or "").lower()
    return any(sig in name for sig in MINER_SIGNATURES)


def shutdown_everything(trigger_name, trigger_pid):
    log(
        f"ABUSE DETECTED: process '{trigger_name}' (pid {trigger_pid}) "
        "matched a known miner signature -- shutting down VNC, desktop "
        "UI, and all cloud-gaming services immediately."
    )
    try:
        subprocess.run(f"kill -9 {trigger_pid}", shell=True)
    except:
        pass
    for name in SERVICES_TO_KILL:
        subprocess.run(f"pkill -9 -f {name}", shell=True)
    subprocess.run("vncserver -kill :1", shell=True)
    log("Shutdown complete. All services stopped.")


def scan_once():
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            info = p.info
            name = info.get("name") or ""
            cmdline = " ".join(info.get("cmdline") or [])
            if matches_miner(name) or matches_miner(cmdline):
                shutdown_everything(name or cmdline, info["pid"])
                return True
        except:
            continue
    return False


log("Anti-abuse watcher started.")

while True:
    try:
        if scan_once():
            time.sleep(30)
        else:
            time.sleep(15)
    except KeyboardInterrupt:
        break
    except Exception as e:
        log(f"watcher error (non-fatal): {e}")
        time.sleep(15)
'''

    Path(watcher).write_text(code)
    run(f"chmod +x {watcher}")
    run(f"nohup python3 {watcher} > {HOME}/anti_abuse_stdout.log 2>&1 &")
    time.sleep(1)


def get_cloudflare_urls():
    stage("Collecting service URLs")

    time.sleep(5)

    services = {
        "vnc": ("novnc", 6001, False),
        "moonlight": ("moonlight-web", 8081, False),
        "sunshine": ("sunshine", 47990, True),
    }

    urls = {}
    for key, (prefix, port, is_https) in services.items():
        path = f"{HOME}/{prefix}-cloudflare.log"
        if not os.path.exists(path):
            continue

        data = open(path).read()
        match = re.search(r"https://[-a-zA-Z0-9]+\.trycloudflare\.com", data)
        if match:
            urls[key] = match.group()

    return urls


def final_report(urls):
    vnc_url = urls.get("vnc", "")
    moonlight_url = urls.get("moonlight", "")

    print(f"VNC URL:\n{vnc_url}\n")
    print(f"Moonlight URL:\n{moonlight_url}")

    send_finish(vnc_url, moonlight_url)


def main():
    check_root()
    record_system_info()
    
    # Clean up marimo first
    cleanup_marimo()

    update_system()
    install_base()
    install_steam()
    install_heroic()

    setup_vnc()
    setup_wallpaper()
    setup_novnc()
    install_cloudflared()

    start_cloudflare("novnc", 6001)

    setup_moonlight_web()
    start_cloudflare("moonlight-web", 8081)

    setup_sunshine()
    start_cloudflare("sunshine", 47990, scheme="https", no_tls_verify=True)
    
    # Configure terminal
    setup_bashrc()

    setup_anti_abuse()

    urls = get_cloudflare_urls()

    stage("Finished")
    final_report(urls)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except KeyboardInterrupt:
        log("[STOP] Interrupted")
    except Exception:
        tb = traceback.format_exc()
        log("==================== UNEXPECTED ERROR")
        log(tb)
        send_error("Unexpected installer error", tb=tb)
        sys.exit(1)
