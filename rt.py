#!/usr/bin/env python3
# cloudgaming_installer.py
# KDE/XFCE + VNC + noVNC + Moonlight Web + Sunshine + Cloudflare
#
# Provisioning agent for cloud gaming platform.
# - Fetches user info from backend at startup
# - Installs and configures services
# - Reports progress via backend API
# - Returns service URLs when complete
# - Exits when done

import os
import sys
import time
import re
import json
import traceback
import subprocess
import shutil
import urllib.request
import sqlite3
from threading import Thread
from pathlib import Path
from datetime import datetime

LOG_FILE  = "/var/log/cloudgaming.log"
STATUS_DB = "/root/.cloudgaming_status.db"

HOME = "/root"
UI   = "kde"

API_URL   = os.getenv("API_URL",   "").rstrip("/")
JOB_TOKEN = os.getenv("JOB_TOKEN", "")

VNC_PASSWORD_GENERATED = None

WALLPAPER_URL = "https://raw.githubusercontent.com/zenixbot0101/Moonlight-Web-2.0/main/wallpaer.jpg"

DEFAULT_USER     = "Aztu"
DEFAULT_PASSWORD = "123456"

# ─── Logging ──────────────────────────────────────────────────────────────────
def log(msg):
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"[{datetime.now()}] {msg}\n")
    except:
        pass

# ─── Status DB ────────────────────────────────────────────────────────────────
def init_status_db():
    try:
        conn   = sqlite3.connect(STATUS_DB)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS status (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT,
                message TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        if JOB_TOKEN:
            cursor.execute("INSERT OR REPLACE INTO status (key,value) VALUES (?,?)", ("job_token", JOB_TOKEN))
            cursor.execute("INSERT OR REPLACE INTO status (key,value) VALUES (?,?)", ("status", "running"))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        log(f"[DB] Init failed: {e}")
        return False

def update_status(key, value):
    try:
        conn = sqlite3.connect(STATUS_DB)
        conn.cursor().execute(
            "INSERT OR REPLACE INTO status (key,value,updated_at) VALUES (?,?,CURRENT_TIMESTAMP)",
            (key, value)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log(f"[DB] Update failed: {e}")

def add_log_entry(level, message):
    try:
        conn = sqlite3.connect(STATUS_DB)
        conn.cursor().execute("INSERT INTO logs (level,message) VALUES (?,?)", (level, message[:500]))
        conn.commit()
        conn.close()
    except Exception as e:
        log(f"[DB] Log failed: {e}")

# ─── Backend API ──────────────────────────────────────────────────────────────
def _post_json(path, payload, timeout=30):
    """Write-only — never receives commands from backend."""
    if not API_URL or not JOB_TOKEN:
        return None
    for attempt in range(3):
        try:
            data = json.dumps(payload).encode()
            req  = urllib.request.Request(
                f"{API_URL}{path}",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            log(f"[API] {path} attempt {attempt+1}/3 failed: {e}")
            if attempt < 2:
                time.sleep(3)
    return None

def _get_json(path, timeout=30):
    """GET request helper."""
    for attempt in range(3):
        try:
            url = f"{API_URL}{path}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            log(f"[API] GET {path} attempt {attempt+1}/3 failed: {e}")
            if attempt < 2:
                time.sleep(3)
    return None

# ─── Heartbeat thread ──────────────────────────────────────────────────────────
_heartbeat_running = False

def _heartbeat_loop():
    """Send heartbeat to server every 10s so server knows script is alive."""
    global _heartbeat_running
    _heartbeat_running = True
    while _heartbeat_running:
        _post_json("/api/heartbeat", {
            "job_token": JOB_TOKEN,
            "message":   "script alive"
        })
        time.sleep(10)

def start_heartbeat():
    """Start heartbeat in background thread."""
    t = Thread(target=_heartbeat_loop, daemon=True)
    t.start()
    log("[HEARTBEAT] Started")

def stop_heartbeat():
    global _heartbeat_running
    _heartbeat_running = False

# ─── Startup: identify user ───────────────────────────────────────────────────
def fetch_user_info():
    """
    Call GET /api/whoami?job_token=<token> to get user info.
    Prints: USER: <username>  INSTALLING...
    """
    if not API_URL or not JOB_TOKEN:
        log("[WHOAMI] API_URL or JOB_TOKEN not set — skipping user fetch")
        print("INSTALLING...")
        return None

    log("[WHOAMI] Fetching user info from backend")
    data = _get_json(f"/api/whoami?job_token={JOB_TOKEN}")

    if data and data.get("ok"):
        user = data.get("user", {})
        username = user.get("username", "unknown")
        email    = user.get("email", "")
        log(f"[WHOAMI] User: {username} ({email})")

        # ── This is what appears in the notebook cell output ──────────────────
        banner = (
            f"\n{'='*50}\n"
            f"  USER: {username}\n"
            f"  EMAIL: {email}\n"
            f"  INSTALLING...\n"
            f"{'='*50}\n"
        )
        print(banner)
        send_progress(f"USER: {username} — Installation starting")
        return user
    else:
        log("[WHOAMI] Could not fetch user info — continuing anyway")
        print("INSTALLING...")
        return None

# ─── Progress reporting ───────────────────────────────────────────────────────
def send_progress(message):
    log(message)
    add_log_entry("info", message)
    _post_json("/api/output", {"job_token": JOB_TOKEN, "message": message})

def send_finish(vnc_url, moonlight_url, sunshine_url=""):
    log(f"FINISH: VNC={vnc_url}, Moonlight={moonlight_url}, Sunshine={sunshine_url}")
    update_status("status",        "completed")
    update_status("vnc_url",       vnc_url)
    update_status("moonlight_url", moonlight_url)
    update_status("sunshine_url",  sunshine_url)
    _post_json("/api/finish", {
        "job_token":     JOB_TOKEN,
        "vnc_url":       vnc_url,
        "moonlight_url": moonlight_url,
        "sunshine_url":  sunshine_url,
    })

def send_error(message, command="", tb=""):
    log(f"ERROR: {message}")
    update_status("status", "failed")
    add_log_entry("error", message[:500])
    _post_json("/api/error", {
        "job_token": JOB_TOKEN,
        "message":   message,
        "command":   command,
        "traceback": tb[:1000] if tb else "",
    })

# ─── Command helpers ──────────────────────────────────────────────────────────
def run(cmd, silent=True, input_data=None, fatal=True):
    try:
        log(f">>> {cmd}")
        result = subprocess.run(
            cmd, shell=True, input=input_data,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        log(f"EXIT CODE: {result.returncode}")
        if result.stdout.strip(): log(f"STDOUT:\n{result.stdout.strip()}")
        if result.stderr.strip(): log(f"STDERR:\n{result.stderr.strip()}")
        if result.returncode != 0:
            raise Exception(result.stderr.strip())
        return result.stdout.strip()
    except Exception as e:
        reason = str(e)
        log(f"COMMAND FAILED: {reason}")
        if fatal:
            send_error(reason, cmd, traceback.format_exc())
            sys.exit(1)
        return None

def snapshot_logs(label, paths):
    for p in paths:
        content = run(f"tail -n 200 {p} 2>/dev/null", silent=True, fatal=False)
        if content:
            log(f"\n----- {label} LOG :: {p} -----\n{content}\n----- end -----\n")

def package_installed(pkg):
    return subprocess.run(f"dpkg -s {pkg}", shell=True,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0

def install_package(pkg):
    if package_installed(pkg):
        log(f"[SKIP] {pkg} already installed"); return
    log(f"[INSTALL] {pkg}")
    run(f"DEBIAN_FRONTEND=noninteractive apt install -y {pkg}", silent=True)

def check_root():
    if os.geteuid() != 0:
        log("ERROR: Must run as root"); sys.exit(1)

def record_system_info():
    for cmd in ["uname -a","cat /etc/os-release","free -h","df -h","lspci | grep -i vga"]:
        run(cmd, silent=True, fatal=False)

# ─── User / system setup ──────────────────────────────────────────────────────
def create_user():
    log(f"[USER] Creating {DEFAULT_USER}")
    run(f"useradd -m -s /bin/bash {DEFAULT_USER}", fatal=False)
    run(f"echo '{DEFAULT_USER}:{DEFAULT_PASSWORD}' | chpasswd", fatal=False)
    run(f"usermod -aG sudo {DEFAULT_USER}", fatal=False)
    run(f'echo "{DEFAULT_USER} ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers', fatal=False)
    run(f"mkdir -p /home/{DEFAULT_USER}", fatal=False)
    run(f"chown -R {DEFAULT_USER}:{DEFAULT_USER} /home/{DEFAULT_USER}", fatal=False)

def change_root_password():
    run(f"echo 'root:{DEFAULT_PASSWORD}' | chpasswd", fatal=False)

# ─── Installation stages ──────────────────────────────────────────────────────
def update_system():
    send_progress("Updating system")
    run("apt update", silent=True)
    run("apt upgrade -y", silent=True)

def install_base():
    send_progress("Installing base packages")
    packages = [
        "tigervnc-standalone-server","dbus-x11","curl","wget",
        "git","chromium","python3-pip","python3-psutil","psmisc"
    ]
    if UI == "xfce":
        packages += ["xfce4","xfce4-goodies","xfce4-terminal"]
    else:
        packages += ["kde-plasma-desktop","plasma-workspace"]
    for p in packages:
        install_package(p)

def install_steam():
    send_progress("Installing Steam")
    run("dpkg --add-architecture i386", fatal=False)
    run("apt update", fatal=False)
    deb = "/tmp/steam.deb"
    run(f"wget -q https://cdn.cloudflare.steamstatic.com/client/installer/steam.deb -O {deb}", fatal=False)
    if os.path.exists(deb):
        run(f"DEBIAN_FRONTEND=noninteractive apt install -y {deb}", fatal=False)

def install_heroic():
    send_progress("Installing Heroic")
    rel = run("curl -s https://api.github.com/repos/Heroic-Games-Launcher/HeroicGamesLauncher/releases/latest", fatal=False)
    if not rel: return
    m = re.search(r'"browser_download_url":\s*"([^"]+amd64\.deb)"', rel)
    if not m: return
    deb = "/tmp/heroic.deb"
    run(f"wget -q {m.group(1)} -O {deb}", fatal=False)
    if os.path.exists(deb):
        run(f"DEBIAN_FRONTEND=noninteractive apt install -y {deb}", fatal=False)

def setup_vnc():
    send_progress("Starting VNC")
    vnc_dir = f"{HOME}/.config/tigervnc"
    run(f"rm -rf {HOME}/.vnc {vnc_dir}")
    run(f"mkdir -p {vnc_dir}")
    global VNC_PASSWORD_GENERATED
    pw = os.environ.get("VNC_PASSWORD","").strip() or "123456"
    VNC_PASSWORD_GENERATED = pw
    run(f"vncpasswd -f > {vnc_dir}/passwd", input_data=pw+"\n")
    run(f"chmod 600 {vnc_dir}/passwd")
    run(f"mkdir -p {HOME}/.vnc")
    run(f"cp {vnc_dir}/passwd {HOME}/.vnc/passwd")
    run(f"chmod 600 {HOME}/.vnc/passwd")
    session_cmd = "startxfce4" if UI=="xfce" else "startplasma-x11"
    startup = f"""#!/bin/bash
unset SESSION_MANAGER
unset DBUS_SESSION_BUS_ADDRESS
xset s off; xset s noblank; xset -dpms
exec dbus-launch --exit-with-session {session_cmd}
"""
    xstartup = f"{vnc_dir}/xstartup"
    Path(xstartup).write_text(startup)
    run(f"chmod +x {xstartup}")
    run("touch /root/.Xauthority; chmod 600 /root/.Xauthority")
    run(f"vncserver :1 -localhost no -geometry 1920x1080 -depth 24 -rfbauth {vnc_dir}/passwd -SecurityTypes VncAuth")
    time.sleep(3)

def disable_screen_lock():
    send_progress("Disabling screen lock")
    if UI == "xfce":
        for ch,prop,val,vt in [
            ("xfce4-screensaver","/saver/enabled","false","bool"),
            ("xfce4-screensaver","/lock/enabled","false","bool"),
            ("xfce4-power-manager","/xfce4-power-manager/dpms-enabled","false","bool"),
        ]:
            run(f"DISPLAY=:1 xfconf-query -c {ch} -p {prop} --create -t {vt} -s {val}", fatal=False)
        run("killall light-locker", fatal=False)
    else:
        for tool in ("kwriteconfig5","kwriteconfig6"):
            for file,grp,key,val in [
                ("kscreenlockerrc","Daemon","Autolock","false"),
                ("kscreenlockerrc","Daemon","Timeout","0"),
            ]:
                run(f"{tool} --file {file} --group {grp} --key {key} {val}", fatal=False)

def setup_shell():
    run(f"echo 'cd ~' >> {HOME}/.bash_profile", fatal=False)

def setup_novnc():
    send_progress("Starting noVNC")
    p = f"{HOME}/noVNC"
    if not os.path.exists(p):
        run(f"cd {HOME} && git clone https://github.com/novnc/noVNC.git")
    run(f"nohup {HOME}/noVNC/utils/novnc_proxy --vnc localhost:5901 --listen 6001 > {HOME}/novnc.log 2>&1 &")
    time.sleep(2)

def install_cloudflared():
    if shutil.which("cloudflared"): return
    run("wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -O /tmp/cloudflared.deb")
    run("apt install -y /tmp/cloudflared.deb")

def start_cloudflare(service, port, scheme="http", no_tls_verify=False):
    send_progress(f"Cloudflare tunnel: {service}")
    log_file = f"{HOME}/{service}-cloudflare.log"
    tls = "--no-tls-verify " if no_tls_verify else ""
    run(f"nohup cloudflared tunnel {tls}--url {scheme}://localhost:{port} > {log_file} 2>&1 &")
    time.sleep(3)

def setup_moonlight_web():
    send_progress("Starting Moonlight Web")
    pkg = f"{HOME}/moonlight-web-x86_64-unknown-linux-gnu.tar.gz"
    if not os.path.exists(pkg):
        run(f"cd {HOME} && wget -q https://github.com/MrCreativ3001/moonlight-web-stream/releases/download/v2.10.0/moonlight-web-x86_64-unknown-linux-gnu.tar.gz")
    run(f"cd {HOME} && tar -xzf moonlight-web-x86_64-unknown-linux-gnu.tar.gz && cd {HOME}/package && chmod +x web-server streamer && nohup ./web-server --bind-address 127.0.0.1:8081 > {HOME}/moonlight-web.log 2>&1 &")
    time.sleep(2)

def setup_sunshine():
    send_progress("Starting Sunshine")
    deb = "/tmp/sunshine.deb"
    if not os.path.exists(deb):
        run("wget -q https://github.com/LizardByte/Sunshine/releases/download/v2026.516.143833/sunshine-debian-trixie-amd64.deb -O /tmp/sunshine.deb")
    run("apt install -y /tmp/sunshine.deb")
    run(f"nohup sunshine > {HOME}/sunshine.log 2>&1 &")
    time.sleep(3)

def setup_wallpaper():
    send_progress("Setting wallpaper")
    dest = f"{HOME}/wallpapers/wallpaper.jpg"
    run(f"mkdir -p {HOME}/wallpapers", fatal=False)
    try:
        urllib.request.urlretrieve(WALLPAPER_URL, dest)
    except Exception as e:
        log(f"[WALLPAPER] Failed: {e}"); return
    run(f"mkdir -p {HOME}/.local/share/wallpapers && cp {dest} {HOME}/.local/share/wallpapers/wallpaper.jpg", fatal=False)

def setup_anti_abuse():
    send_progress("Starting anti-abuse watcher")
    watcher = f"{HOME}/anti_abuse.py"
    code = r'''
import psutil, time, subprocess, os
from datetime import datetime

LOG = os.path.expanduser("~/anti_abuse.log")
MINERS = ["xmrig","xmr-stak","cpuminer","minerd","ccminer","ethminer",
          "t-rex","nbminer","gminer","lolminer","teamredminer"]
KILL   = ["Xtigervnc","vncserver","startplasma-x11","startxfce4",
          "web-server","sunshine","cloudflared","novnc_proxy"]

def _log(msg):
    line = f"[{datetime.now()}] {msg}"
    print(line)
    try:
        with open(LOG,"a") as f: f.write(line+"\n")
    except: pass

def _matches(name):
    n=(name or "").lower()
    return any(s in n for s in MINERS)

def _shutdown(name, pid):
    _log(f"ABUSE: {name} pid={pid}")
    subprocess.run(f"kill -9 {pid}", shell=True)
    for s in KILL: subprocess.run(f"pkill -9 -f {s}", shell=True)
    subprocess.run("vncserver -kill :1", shell=True)

def scan():
    for p in psutil.process_iter(["pid","name","cmdline"]):
        try:
            info=p.info
            n=info.get("name") or ""
            c=" ".join(info.get("cmdline") or [])
            if _matches(n) or _matches(c):
                _shutdown(n or c, info["pid"]); return True
        except: continue
    return False

_log("Anti-abuse watcher started.")
while True:
    try:
        time.sleep(30 if scan() else 15)
    except KeyboardInterrupt: break
    except Exception as e: _log(f"error: {e}"); time.sleep(15)
'''
    Path(watcher).write_text(code)
    run(f"chmod +x {watcher}")
    run(f"nohup python3 {watcher} > {HOME}/anti_abuse_stdout.log 2>&1 &")
    time.sleep(1)

def get_cloudflare_urls():
    send_progress("Collecting Cloudflare URLs")
    time.sleep(5)
    services = {
        "VNC":       ("novnc",        6001),
        "Moonlight": ("moonlight-web",8081),
        "Sunshine":  ("sunshine",  47990),
    }
    urls = {}
    for label,(prefix,_) in services.items():
        path = f"{HOME}/{prefix}-cloudflare.log"
        if not os.path.exists(path): continue
        m = re.search(r"https://[-a-zA-Z0-9]+\.trycloudflare\.com", open(path).read())
        if m: urls[label] = m.group()
    return urls

def final_report(urls):
    vnc_url       = urls.get("VNC","")
    moonlight_url = urls.get("Moonlight","")
    sunshine_url  = urls.get("Sunshine","")
    output = f"""
{'='*50}
 CLOUD GAMING READY
{'='*50}
🔗 VNC URL:
{vnc_url}

🌙 Moonlight URL:
{moonlight_url}

☀️  Sunshine URL:
{sunshine_url}

👤 User: {DEFAULT_USER}
🔑 Password: {DEFAULT_PASSWORD}
{'='*50}
"""
    print(output)
    send_finish(vnc_url, moonlight_url, sunshine_url)

def create_monitor():
    monitor = f"{HOME}/cloud-monitor.py"
    Path(monitor).write_text(r'''
import psutil, time, subprocess, os
from datetime import datetime

APPS = {"steam":"Steam","heroic":"Heroic","chromium":"Chromium",
        "sunshine":"Sunshine","Xtigervnc":"TigerVNC","web-server":"Moonlight"}
URLS = os.path.expanduser("~/.cloudgaming_urls")

def load_urls():
    if not os.path.exists(URLS): return []
    return [l.split("|") for l in open(URLS).read().splitlines() if l.count("|")==3]

while True:
    print("\033c")
    print("="*30+"\n CLOUD GAMING MONITOR\n"+"="*30)
    print("TIME:", datetime.now())
    u=time.time()-psutil.boot_time(); h=int(u//3600); m=int((u%3600)//60)
    print(f"UPTIME: {h}h {m}m\n\nACCESS URLS\n")
    for label,url,port,scheme in load_urls():
        print(f"{label:<22} {url}")
    print("\nAPPS\n")
    names=[p.info["name"] for p in psutil.process_iter(["name"]) if p.info["name"]]
    for k,n in APPS.items():
        print(f"{n:<15} {'RUNNING' if any(k.lower() in x.lower() for x in names) else 'STOPPED'}")
    mem=psutil.virtual_memory()
    print(f"\nCPU: {psutil.cpu_percent()}%  RAM: {mem.used//1024**3}/{mem.total//1024**3}GB")
    print("\n(Ctrl+C to exit)")
    time.sleep(10)
''')
    run(f"chmod +x {monitor}")
    log("[MONITOR] Created at ~/cloud-monitor.py")

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    check_root()
    init_status_db()
    update_status("started_at", str(datetime.now()))
    record_system_info()

    # ── Step 0: Start heartbeat so server knows script is alive ───────────────
    start_heartbeat()

    # ── Step 1: Identify user ─────────────────────────────────────────────────
    fetch_user_info()

    # ── Installation ──────────────────────────────────────────────────────────
    create_user()
    change_root_password()
    update_system()
    install_base()
    install_steam()
    install_heroic()
    setup_vnc()
    disable_screen_lock()
    setup_shell()
    setup_novnc()
    install_cloudflared()
    start_cloudflare("novnc", 6001)
    setup_moonlight_web()
    start_cloudflare("moonlight-web", 8081)
    setup_sunshine()
    start_cloudflare("sunshine", 47990, scheme="https", no_tls_verify=True)
    setup_wallpaper()
    setup_anti_abuse()

    urls = get_cloudflare_urls()
    Path(f"{HOME}/.cloudgaming_urls").write_text(
        "\n".join(f"{k}|{v}|0|http" for k,v in urls.items())
    )
    create_monitor()
    final_report(urls)

    log("[INSTALL] Complete")
    update_status("completed_at", str(datetime.now()))
    update_status("exit_code", "0")
    sys.exit(0)

if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except KeyboardInterrupt:
        log("[STOP] Interrupted")
        update_status("status", "interrupted")
        sys.exit(1)
    except Exception:
        tb = traceback.format_exc()
        log(f"UNEXPECTED ERROR:\n{tb}")
        send_error(str(sys.exc_info()[1]), "", tb)
        update_status("status", "failed")
        sys.exit(1)
