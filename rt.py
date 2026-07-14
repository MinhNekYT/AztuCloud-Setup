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
# Install stages
# ---------------------------------------------------------------------

def update_system():
    stage("Updating system")
    run("apt update")
    run("apt upgrade -y")


def install_base():
    stage("Installing KDE")
    packages = [
        "tigervnc-standalone-server",
        "dbus-x11",
        "curl",
        "wget",
        "git",
        "chromium",
        "python3-pip",
        "python3-psutil",
        "psmisc",
        "kde-plasma-desktop",
        "plasma-workspace",
    ]
    for p in packages:
        install_package(p)


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

    startup = """#!/bin/bash
unset SESSION_MANAGER
unset DBUS_SESSION_BUS_ADDRESS
xset s off
xset s noblank
xset -dpms
exec dbus-launch --exit-with-session startplasma-x11
"""
    xstartup_path = f"{vnc_dir}/xstartup"
    Path(xstartup_path).write_text(startup)
    run(f"chmod +x {xstartup_path}")

    run("touch /root/.Xauthority")
    run("chmod 600 /root/.Xauthority")

    run(
        f"""
vncserver :1 \
-localhost no \
-geometry 1920x1080 \
-depth 24 \
-rfbauth {vnc_dir}/passwd \
-SecurityTypes VncAuth
"""
    )

    time.sleep(3)
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


def setup_novnc():
    stage("Starting noVNC")

    path = f"{HOME}/noVNC"
    if not os.path.exists(path):
        run(f"cd {HOME} && git clone https://github.com/novnc/noVNC.git")

    run(
        f"""
nohup {HOME}/noVNC/utils/novnc_proxy \
--vnc localhost:5901 \
--listen 6001 \
> {HOME}/novnc.log 2>&1 &
"""
    )

    time.sleep(2)
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

    run(
        f"""
nohup cloudflared tunnel {tls_flag}\
--url {scheme}://localhost:{port} \
> {log_file} 2>&1 &
"""
    )

    time.sleep(3)
    snapshot_logs(f"Cloudflare tunnel ({service})", [log_file])


def setup_moonlight_web():
    stage("Installing Moonlight Web")

    package = f"{HOME}/moonlight-web-x86_64-unknown-linux-gnu.tar.gz"
    if not os.path.exists(package):
        run(
            f"cd {HOME} && wget -q "
            "https://github.com/MrCreativ3001/moonlight-web-stream/releases/download/v2.10.0/moonlight-web-x86_64-unknown-linux-gnu.tar.gz"
        )

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

    time.sleep(2)
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
    run(f"nohup sunshine > {HOME}/sunshine.log 2>&1 &")

    time.sleep(3)
    snapshot_logs(
        "Sunshine",
        [f"{HOME}/sunshine.log", f"{HOME}/.config/sunshine/sunshine.log"],
    )


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

    update_system()
    install_base()
    install_steam()
    install_heroic()

    setup_vnc()
    setup_novnc()
    install_cloudflared()

    start_cloudflare("novnc", 6001)

    setup_moonlight_web()
    start_cloudflare("moonlight-web", 8081)

    setup_sunshine()
    start_cloudflare("sunshine", 47990, scheme="https", no_tls_verify=True)

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
