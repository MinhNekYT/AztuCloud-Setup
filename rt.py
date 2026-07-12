#!/usr/bin/env python3
# cloudgaming_installer.py
# KDE/XFCE + VNC + noVNC + Moonlight Web + Sunshine + Cloudflare + Monitor

import os
import sys
import time
import re
import traceback
import subprocess
import shutil
import getpass
import secrets
import platform
import urllib.request
from pathlib import Path
from datetime import datetime


LOG_FILE = "/var/log/cloudgaming.log"

# Everything now runs as root, in root's own home -- no separate
# Linux user is created anymore.
HOME = "/root"

# Set by choose_ui() before anything else installs. "kde" = full KDE
# Plasma desktop, "xfce" = lightweight XFCE (much lower RAM/CPU
# footprint, better for small/cheap VPS boxes).
UI = "kde"

# Set by setup_vnc() when it has to fall back to auto-generating the VNC
# password (no usable tty to prompt on) instead of an interactive answer,
# so final_report() can print it back to the user -- otherwise they'd have
# no way to know what it is.
VNC_PASSWORD_GENERATED = None


def log(msg):
    try:
        with open(LOG_FILE, "a") as f:
            f.write(
                f"[{datetime.now()}] {msg}\n"
            )
    except:
        pass


def out(msg):
    print(msg)
    log(msg)


def run(cmd, silent=False, input_data=None, fatal=True):
    try:
        if not silent:
            out(f">>> {cmd}")
        else:
            # Keep the console output compact, but the full command
            # always still goes into the log file so a later "what
            # happened during install" investigation isn't missing
            # anything just because it succeeded quietly.
            log(f">>> {cmd}")

        result = subprocess.run(
            cmd,
            shell=True,
            input=input_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # Always record full stdout/stderr/exit code to the log file,
        # success or failure. This is what makes it possible to debug
        # a VNC/Sunshine problem later -- by the time something looks
        # wrong, the moment it actually broke is long past, so nothing
        # useful can be silently dropped here.
        log(f"EXIT CODE: {result.returncode}")

        if result.stdout.strip():
            log(f"STDOUT:\n{result.stdout.strip()}")

        if result.stderr.strip():
            log(f"STDERR:\n{result.stderr.strip()}")

        if result.returncode != 0:
            raise Exception(
                result.stderr.strip()
            )

        return result.stdout.strip()

    except Exception as e:
        out("\n====================")
        out("ERROR" if fatal else "WARNING (non-fatal, continuing)")
        out("====================")
        out(f"COMMAND:\n{cmd}")
        out(f"REASON:\n{e}")
        if fatal:
            sys.exit(1)
        return None


def snapshot_logs(label, paths):
    # Tails a list of service log files (globs allowed) into the
    # central /var/log/cloudgaming.log with clear headers. Run this
    # after starting each background service (VNC, Sunshine, noVNC,
    # Moonlight Web, Cloudflare tunnels) so that if one of them is
    # broken, there's already a labeled copy of its own log sitting in
    # one place instead of having to go hunt through the user's home
    # directory for it.
    for p in paths:

        content = run(
            f"tail -n 200 {p} 2>/dev/null",
            silent=True,
            fatal=False
        )

        if content:
            log(
                f"\n----- {label} LOG :: {p} -----\n{content}\n----- end {label} log -----\n"
            )


def package_installed(pkg):
    result = subprocess.run(
        f"dpkg -s {pkg}",
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    return result.returncode == 0


def install_package(pkg):
    if package_installed(pkg):
        out(f"[SKIP] {pkg} already installed")
        return

    out(
        f"[INSTALL] Hãy đợi 5 phút, đang cài {pkg}..."
    )

    run(
        f"DEBIAN_FRONTEND=noninteractive apt install -y {pkg}",
        silent=True
    )


def check_root():
    if os.geteuid() != 0:
        out("ERROR: Run with sudo/root")
        sys.exit(1)


def record_system_info():
    # Written once at the very start of every run, so that if VNC or
    # Sunshine acts up weeks later, the log still shows exactly what
    # OS/kernel/hardware/free-space situation the install happened
    # under -- most "works on my machine" VNC/Sunshine bugs turn out
    # to be OS-version or out-of-disk-space related.
    out("[LOG] Recording system info for future troubleshooting")

    for cmd in [
        "uname -a",
        "cat /etc/os-release",
        "free -h",
        "df -h",
        "lspci | grep -i vga",
    ]:
        run(cmd, silent=True, fatal=False)


def choose_ui():

    global UI

    out(
        "\n=============================="
    )

    out(
        "CHOOSE DESKTOP UI"
    )

    out(
        "=============================="
    )

    print("""
  1) KDE Plasma  - full-featured, heavier (more RAM/CPU)
  2) XFCE Lite   - lightweight, faster over VNC on small/cheap boxes
""")

    choice = input(
        "Chọn UI [1-2] (mặc định 1 = KDE): "
    ).strip()

    UI = "xfce" if choice == "2" else "kde"

    out(
        f"[UI] Selected: {'XFCE Lite' if UI == 'xfce' else 'KDE Plasma'}"
    )


def check_region():

    out("[CHECK] Region")

    try:
        country = run(
            "curl -s https://ipinfo.io/country",
            silent=True
        )

        out(
            f"Detected country: {country}"
        )

    except:
        out(
            "Cannot detect IP region"
        )


def update_system():

    out(
        "[UPDATE] Hãy đợi, đang update system..."
    )

    run(
        "apt update",
        silent=True
    )

    run(
        "apt upgrade -y",
        silent=True
    )


def install_base():

    packages = [
        "tigervnc-standalone-server",
        "dbus-x11",
        "curl",
        "wget",
        "git",
        "chromium",
        "python3-pip",
        "python3-psutil",
        "psmisc"
    ]

    if UI == "xfce":

        out(
            "[UI] Installing XFCE Lite (xfce4 + xfce4-goodies)"
        )

        packages += [
            "xfce4",
            "xfce4-goodies",
            "xfce4-terminal",
        ]

    else:

        out(
            "[UI] Installing KDE Plasma"
        )

        packages += [
            "kde-plasma-desktop",
            "plasma-workspace",
        ]

    for p in packages:
        install_package(p)



def install_steam():

    out(
        "[STEAM] Installing (best-effort, will skip on error)"
    )

    # Steam needs the i386 architecture enabled on a 64-bit Debian box.
    # Any failure here is non-fatal -- worst case Steam's own .deb
    # install below fails too and we just move on, per "nếu lỗi thì
    # có thể skip".
    run(
        "dpkg --add-architecture i386",
        silent=True,
        fatal=False
    )

    run(
        "apt update",
        silent=True,
        fatal=False
    )

    deb = "/tmp/steam.deb"

    run(
        f"wget -q https://cdn.cloudflare.steamstatic.com/client/installer/steam.deb -O {deb}",
        silent=True,
        fatal=False
    )

    if os.path.exists(deb):

        run(
            f"DEBIAN_FRONTEND=noninteractive apt install -y {deb}",
            silent=True,
            fatal=False
        )

    else:

        out(
            "[SKIP] Steam download failed, continuing without it"
        )



def install_heroic():

    out(
        "[HEROIC] Installing (best-effort, will skip on error)"
    )

    # Resolve the latest .deb asset from GitHub releases instead of
    # hardcoding a version -- Heroic's release filenames are versioned,
    # so a fixed URL would go stale.
    release_json = run(
        "curl -s https://api.github.com/repos/Heroic-Games-Launcher/HeroicGamesLauncher/releases/latest",
        silent=True,
        fatal=False
    )

    if not release_json:

        out(
            "[SKIP] Could not reach GitHub for Heroic release info"
        )

        return

    match = re.search(
        r'"browser_download_url":\s*"([^"]+amd64\.deb)"',
        release_json
    )

    if not match:

        out(
            "[SKIP] Could not find a Heroic .deb asset in the latest release"
        )

        return

    url = match.group(1)
    deb = "/tmp/heroic.deb"

    run(
        f"wget -q {url} -O {deb}",
        silent=True,
        fatal=False
    )

    if os.path.exists(deb):

        run(
            f"DEBIAN_FRONTEND=noninteractive apt install -y {deb}",
            silent=True,
            fatal=False
        )

    else:

        out(
            "[SKIP] Heroic download failed, continuing without it"
        )



def setup_vnc():

    out(
        "[VNC] Setup"
    )

    vnc_dir = f"{HOME}/.config/tigervnc"

    # Newer TigerVNC (>=1.13) stores its config in ~/.config/tigervnc
    # instead of ~/.vnc, and auto-migrates ~/.vnc there the first time
    # vncserver runs. That migration breaks if ~/.config doesn't exist
    # yet (fresh user account) or if ~/.config/tigervnc already exists
    # partially from an earlier failed run of this script. Fix: wipe
    # any leftover state and write straight into the new location, so
    # there's nothing left for vncserver to "migrate".
    run(
        f"rm -rf {HOME}/.vnc {vnc_dir}",
        silent=True
    )

    run(
        f"mkdir -p {vnc_dir}"
    )

    # Plain `vncpasswd` needs a real tty (it uses ioctl to disable echo
    # while you type). That fails with "Inappropriate ioctl for device"
    # when this script runs from a notebook/non-interactive shell.
    # Fix: read the password ourselves with getpass (works without a
    # tty) and pipe it into `vncpasswd -f`, which reads plaintext from
    # stdin and writes the obfuscated password file to stdout instead
    # of prompting.
    #
    # Further fix: some launch methods (e.g. `exec(urlopen(...).read())`
    # inside a notebook cell) have *no* controlling tty and no readable
    # stdin at all, so even getpass's own fallback path raises (its
    # attempt to open /dev/tty errors with "Inappropriate ioctl for
    # device", or a wrapping notebook runtime raises its own error first).
    # In that situation there is no way to prompt interactively, so:
    #   1. Allow the password to be supplied non-interactively via the
    #      VNC_PASSWORD environment variable.
    #   2. Otherwise try the interactive prompt.
    #   3. If that also fails for any reason, auto-generate a random
    #      password instead of crashing, and print it in the final
    #      report so the user can still log in.
    global VNC_PASSWORD_GENERATED

    vnc_password = os.environ.get("VNC_PASSWORD", "").strip()

    if not vnc_password:

        try:

            vnc_password = getpass.getpass(
                "VNC password (min 6 chars): "
            )

        except Exception as e:

            vnc_password = secrets.token_urlsafe(9)

            VNC_PASSWORD_GENERATED = vnc_password

            out(
                "[VNC] No interactive terminal available "
                f"({e}) -- auto-generated a VNC password instead. "
                "It will be printed in the final summary."
            )

    if not vnc_password:

        vnc_password = secrets.token_urlsafe(9)

        VNC_PASSWORD_GENERATED = vnc_password

    run(
        f"vncpasswd -f > {vnc_dir}/passwd",
        input_data=vnc_password + "\n"
    )

    run(
        f"chmod 600 {vnc_dir}/passwd"
    )


    # Two fixes here, both needed for the desktop session to survive on
    # TigerVNC, whichever UI was chosen:
    # 1. `exec` instead of `<session> &` — backgrounding makes the
    #    xstartup script itself return immediately, which vncserver
    #    treats as "session exited too early" and kills it. `exec`
    #    replaces the shell process with the desktop session so the
    #    script never returns while the session is alive.
    # 2. `dbus-launch --exit-with-session` — both KDE Plasma and XFCE
    #    need a D-Bus session bus to start; without one they crash
    #    within seconds.
    # 3. `xset s off/-dpms/s noblank` — fixes the classic "blackscreen
    #    but the machine is still working" bug on TigerVNC: X11's own
    #    screensaver/blanking still fires on a VNC display even though
    #    there's no real monitor to blank, and it paints the captured
    #    framebuffer black. Disabling blanking/DPMS/screensaver at the
    #    X server level up front stops that from ever kicking in.
    session_cmd = "startxfce4" if UI == "xfce" else "startplasma-x11"

    startup = f"""#!/bin/bash
unset SESSION_MANAGER
unset DBUS_SESSION_BUS_ADDRESS
xset s off
xset s noblank
xset -dpms
exec dbus-launch --exit-with-session {session_cmd}
"""


    xstartup_path = f"{vnc_dir}/xstartup"

    Path(xstartup_path).write_text(startup)

    run(
        f"chmod +x {xstartup_path}"
    )

    # TigerVNC's vncserver wrapper calls `xauth` to set up X11 auth
    # before it can start Xvnc. Pre-creating ~/.Xauthority up front
    # sidesteps the "xauth can't create the file" failure mode that
    # otherwise makes the whole session exit within seconds.
    run(
        "touch /root/.Xauthority"
    )

    run(
        "chmod 600 /root/.Xauthority"
    )


    # NOTE: do NOT pass "-xstartup <session command>" here.
    # vncserver's -xstartup flag expects a *path to a script*, not a
    # command name. Passing a bare command breaks startup and silently
    # overrides the xstartup file we just wrote above. Leaving -xstartup
    # out lets vncserver fall back to the default xstartup file, which
    # already runs the chosen desktop session correctly.
    #
    # Running vncserver directly as root (no `su`) is what makes
    # "ALL IN ROOT" possible -- TigerVNC and both desktop UIs work
    # fine as root, they just normally aren't run that way.
    run(
        """
vncserver :1 \
-localhost no \
-geometry 1920x1080 \
-depth 24
"""
    )

    # Give Xvnc/Plasma a moment to either settle or crash, then copy
    # whatever it wrote into the central log. This is the single most
    # useful log for diagnosing "VNC won't start" / "black screen" /
    # "Plasma crashed" reports later.
    time.sleep(3)

    snapshot_logs(
        "VNC (:1)",
        [
            f"{HOME}/.vnc/*:1.log",
            f"{HOME}/.config/tigervnc/*:1.log",
        ]
    )



def disable_screen_lock():

    if UI == "xfce":
        disable_screen_lock_xfce()
    else:
        disable_screen_lock_kde()


def disable_screen_lock_kde():

    out(
        "[LOCKSCREEN] Disabling KDE screen lock + power blanking "
        "(so an idle VNC session never shows the lock screen or goes black)"
    )

    # Best-effort across both Plasma 5 (kwriteconfig5) and Plasma 6
    # (kwriteconfig6, likely what ships on Debian trixie) -- whichever
    # tool doesn't exist on this system just fails silently and we move
    # on, keeping the output compact.
    tools = ["kwriteconfig5", "kwriteconfig6"]

    settings = [
        # Kill the lock screen entirely -- this is the dialog shown in
        # the screenshot after the VNC session sits idle for a while.
        ("kscreenlockerrc", "Daemon", "Autolock", "false"),
        ("kscreenlockerrc", "Daemon", "LockOnResume", "false"),
        ("kscreenlockerrc", "Daemon", "Timeout", "0"),
        # Disable screen blanking / DPMS / suspend triggers on both AC
        # and battery profiles so power management never blacks out the
        # session either.
        ("powermanagementprofilesrc", "AC;DPMSControl", "idleTime", "0"),
        ("powermanagementprofilesrc", "AC;DPMSControl", "enabled", "false"),
        ("powermanagementprofilesrc", "AC;SuspendSession", "idleTime", "0"),
        ("powermanagementprofilesrc", "AC;SuspendSession", "suspendThenHibernate", "false"),
        ("powermanagementprofilesrc", "Battery;DPMSControl", "idleTime", "0"),
        ("powermanagementprofilesrc", "Battery;DPMSControl", "enabled", "false"),
        ("powermanagementprofilesrc", "Battery;SuspendSession", "idleTime", "0"),
        ("powermanagementprofilesrc", "Battery;SuspendSession", "suspendThenHibernate", "false"),
    ]

    for tool in tools:

        for file, group, key, value in settings:

            group_flags = " ".join(
                f"--group {g}" for g in group.split(";")
            )

            run(
                f"{tool} --file {file} {group_flags} --key {key} {value}",
                silent=True,
                fatal=False
            )


def disable_screen_lock_xfce():

    out(
        "[LOCKSCREEN] Disabling XFCE screen lock + power blanking "
        "(so an idle VNC session never shows the lock screen or goes black)"
    )

    # XFCE's screensaver/lock and power management live in xfconf, set
    # via xfconf-query instead of KDE's kwriteconfig. xfce4-screensaver
    # (or light-locker, depending on what's installed) is what shows
    # the lock dialog; xfce4-power-manager is what blanks/suspends.
    settings = [
        ("xfce4-screensaver", "/saver/enabled", "false", "bool"),
        ("xfce4-screensaver", "/lock/enabled", "false", "bool"),
        ("xfce4-power-manager", "/xfce4-power-manager/dpms-enabled", "false", "bool"),
        ("xfce4-power-manager", "/xfce4-power-manager/blank-on-ac", "0", "int"),
        ("xfce4-power-manager", "/xfce4-power-manager/dpms-on-ac-sleep", "0", "int"),
        ("xfce4-power-manager", "/xfce4-power-manager/dpms-on-ac-off", "0", "int"),
        ("xfce4-power-manager", "/xfce4-power-manager/inactivity-on-ac", "0", "int"),
    ]

    for channel, prop, value, vtype in settings:

        run(
            f"DISPLAY=:1 xfconf-query -c {channel} -p {prop} "
            f"--create -t {vtype} -s {value}",
            silent=True,
            fatal=False
        )

    # Also disable light-locker if it's the one installed instead of
    # xfce4-screensaver -- easiest to just make sure it's not running.
    run(
        "killall light-locker",
        silent=True,
        fatal=False
    )



def setup_novnc():

    out(
        "[noVNC] Installing"
    )

    path=f"{HOME}/noVNC"


    if not os.path.exists(path):

        run(
            f"cd {HOME} && git clone https://github.com/novnc/noVNC.git"
        )

    else:
        out(
            "[SKIP] noVNC exists"
        )


    run(
        f"""
nohup {HOME}/noVNC/utils/novnc_proxy \
--vnc localhost:5901 \
--listen 6001 \
> {HOME}/novnc.log 2>&1 &
"""
    )

    time.sleep(2)

    snapshot_logs(
        "noVNC",
        [f"{HOME}/novnc.log"]
    )


def install_cloudflared():

    if shutil.which(
        "cloudflared"
    ):
        out(
            "[SKIP] cloudflared exists"
        )
        return


    out(
        "[INSTALL] cloudflared"
    )

    run(
        """
wget -q \
https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb \
-O /tmp/cloudflared.deb
"""
    )


    run(
        "apt install -y /tmp/cloudflared.deb",
        silent=True
    )
def start_cloudflare(service, port, scheme="http", no_tls_verify=False):

    out(
        f"[CLOUDFLARE] Starting {service}:{port}"
    )

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

    snapshot_logs(
        f"Cloudflare tunnel ({service})",
        [log_file]
    )


def setup_moonlight_web():

    out(
        "[MOONLIGHT WEB] Installing"
    )

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

    snapshot_logs(
        "Moonlight Web",
        [f"{HOME}/moonlight-web.log"]
    )



def setup_sunshine():

    out(
        "[SUNSHINE] Installing"
    )


    deb="/tmp/sunshine.deb"


    if not os.path.exists(deb):

        run(
            """
wget -q \
https://github.com/LizardByte/Sunshine/releases/download/v2026.516.143833/sunshine-debian-trixie-amd64.deb \
-O /tmp/sunshine.deb
"""
        )


    run(
        "apt install -y /tmp/sunshine.deb",
        silent=True
    )


    out(
        "[SUNSHINE] Starting"
    )


    run(
        f"""
nohup sunshine \
> {HOME}/sunshine.log 2>&1 &
"""
    )

    time.sleep(3)

    # Sunshine keeps its own internal log (separate from the nohup
    # wrapper's stdout/stderr capture above) -- both are worth having
    # on hand since Sunshine problems tend to show up in one but not
    # the other.
    snapshot_logs(
        "Sunshine",
        [
            f"{HOME}/sunshine.log",
            f"{HOME}/.config/sunshine/sunshine.log",
        ]
    )



def setup_wallpaper():

    out(
        "[WALLPAPER] Download"
    )


    file=f"{HOME}/wallpaper.png"


    if not os.path.exists(file):

        urllib.request.urlretrieve(
            "https://raw.githubusercontent.com/zenixbot0101/Sunshine-Pair-CLI/main/wallapper.png",
            file
        )


    run(
        f"""
mkdir -p {HOME}/.local/share/wallpapers

cp {file} \
{HOME}/.local/share/wallpapers/wallpaper.png
"""
    )

    # Applying the wallpaper live requires talking to the already
    # running desktop session over D-Bus/X11. This is a fresh shell
    # (separate from the VNC session's environment), so it doesn't
    # automatically know DISPLAY or the right D-Bus session bus —
    # setting DISPLAY=:1 covers the common case, but this can still
    # fail depending on timing. It's purely cosmetic (the file is
    # already copied in place above and can be set manually later),
    # so a failure here shouldn't abort the whole install.
    if UI == "xfce":

        run(
            f"DISPLAY=:1 xfconf-query -c xfce4-desktop "
            f"-p /backdrop/screen0/monitor0/workspace0/last-image "
            f"--create -t string -s {HOME}/.local/share/wallpapers/wallpaper.png",
            fatal=False
        )

    else:

        run(
            f"DISPLAY=:1 plasma-apply-wallpaperimage {HOME}/.local/share/wallpapers/wallpaper.png",
            fatal=False
        )



def create_monitor(urls):

    out(
        "[MONITOR] Creating app monitor"
    )


    monitor=f"{HOME}/cloud-monitor.py"


    code=r'''
import psutil
import time
import subprocess
import os
from datetime import datetime


apps={
"steam":"Steam",
"heroic":"Heroic",
"chromium":"Chromium",
"sunshine":"Sunshine",
"Xorg":"X11",
"Xtigervnc":"TigerVNC",
"web-server":"Moonlight"
}


URLS_FILE = os.path.expanduser("~/.cloudgaming_urls")


def load_urls():

    entries = []

    if os.path.exists(URLS_FILE):

        with open(URLS_FILE) as f:

            for line in f:

                line = line.strip()

                if not line:
                    continue

                parts = line.split("|")

                if len(parts) == 4:
                    entries.append(parts)

    return entries


while True:

    print("\033c")

    print("==============================")
    print(" CLOUD GAMING MONITOR")
    print("==============================")

    print(
        "TIME:",
        datetime.now()
    )


    uptime=time.time()-psutil.boot_time()

    h=int(uptime//3600)
    m=int((uptime%3600)//60)

    print(
        f"UPTIME: {h}h {m}m"
    )


    print("\nACCESS URLS\n")

    entries = load_urls()

    if entries:

        for label, url, port, local_scheme in entries:

            print(f"{label:<22} {url}")
            print(f"{'':<22} (local: {local_scheme}://localhost:{port})")

    else:

        print("(chua co tunnel nao san sang)")


    print("\nAPPLICATION STATUS\n")


    processes=[
        p.info
        for p in psutil.process_iter(
            ["name"]
        )
    ]


    names=[
        x["name"]
        for x in processes
        if x["name"]
    ]


    for key,name in apps.items():

        status="STOPPED"

        for p in names:

            if key.lower() in p.lower():
                status="RUNNING"


        print(
            f"{name:<15} {status}"
        )


    print("\nSYSTEM")


    print(
        "CPU:",
        psutil.cpu_percent(),
        "%"
    )


    mem=psutil.virtual_memory()

    print(
        "RAM:",
        round(mem.used/1024**3,2),
        "/",
        round(mem.total/1024**3,2),
        "GB"
    )


    try:

        gpu=subprocess.check_output(
            "nvidia-smi --query-gpu=name --format=csv,noheader",
            shell=True
        ).decode().strip()


        print(
            "GPU:",
            gpu
        )

    except:

        pass


    print("\n(Ctrl+C thoat monitor - cac dich vu van chay ngam)")


    time.sleep(10)
'''

    Path(monitor).write_text(code)

    run(
        f"chmod +x {monitor}"
    )

    # URLs are saved separately by get_cloudflare_urls() into
    # ~/.cloudgaming_urls, which the monitor script above reads on
    # every refresh — so it stays correct even though this function
    # doesn't launch the monitor itself (main() does that in the
    # foreground as the final step).



def get_cloudflare_urls():

    out(
        "\n[CLOUDFLARE URL]"
    )

    time.sleep(5)

    # label -> (log file prefix, local port, is displayed as https)
    services = {
        "noVNC (VNC Desktop)": ("novnc", 6001, False),
        "Moonlight Web":       ("moonlight-web", 8081, False),
        "Sunshine":            ("sunshine", 47990, True),
    }

    urls = {}

    for label, (prefix, port, is_https) in services.items():

        path = f"{HOME}/{prefix}-cloudflare.log"

        if not os.path.exists(path):
            continue

        data = open(path).read()

        match = re.search(
            r"https://[-a-zA-Z0-9]+\.trycloudflare\.com",
            data
        )

        if match:
            urls[label] = {
                "url": match.group(),
                "port": port,
                "local_scheme": "https" if is_https else "http"
            }

    # Save for the monitor script to pick up (it runs as a separate
    # process, so it can't just read this dict from memory).
    lines = [
        f"{label}|{info['url']}|{info['port']}|{info['local_scheme']}"
        for label, info in urls.items()
    ]

    urls_file = f"{HOME}/.cloudgaming_urls"

    Path(urls_file).write_text("\n".join(lines))

    if not urls:
        out(
            "Chưa lấy được URL Cloudflare nào (tunnel có thể cần thêm vài giây)."
        )

    return urls



def moonlight_pair():

    out(
        "\n=============================="
    )

    out(
        "MOONLIGHT PAIR"
    )

    out(
        "=============================="
    )


    pin=input(
        "Enter Moonlight PIN: "
    )


    run(
        f"""
curl -u admin:admin \
-X POST -k https://localhost:47990/api/password \
-H "Content-Type: application/json" \
-d '{{"currentUsername":"admin","currentPassword":"admin","newUsername":"admin","newPassword":"admin","confirmNewPassword":"admin"}}'
"""
    )


    run(
        f"""
curl -u admin:admin \
-X POST -k https://localhost:47990/api/pin \
-H "Content-Type: application/json" \
-d '{{"pin":"{pin}","name":"moonlight"}}'
"""
    )


    out(
        "Moonlight Pair Success!"
    )



def final_report(urls):

    ui_label = "XFCE Lite" if UI == "xfce" else "KDE Plasma"

    if VNC_PASSWORD_GENERATED:

        print(f"""

========================================

 VNC PASSWORD (auto-generated -- no
 interactive prompt was available)

========================================

  {VNC_PASSWORD_GENERATED}

Save this now -- it is not stored anywhere in plaintext.
""")

    print(f"""

========================================

 CLOUD GAMING READY

========================================

Services:

[OK] Desktop UI ({ui_label})
[OK] TigerVNC
[OK] noVNC
[OK] Moonlight Web
[OK] Sunshine
[OK] Chromium
[OK] Cloudflare Tunnel
[OK] Running as root (no separate Linux user)
[OK] Screen lock + screen blanking disabled

""")

    if urls:

        print("ACCESS URLS:\n")

        for label, info in urls.items():

            print(
                f"  {label:<22} {info['url']}"
            )
            print(
                f"  {'':<22} (local: {info['local_scheme']}://localhost:{info['port']})"
            )

        print()

    else:

        print(
            "(Chưa lấy được URL Cloudflare — kiểm tra lại các file "
            "*-cloudflare.log trong thư mục home)\n"
        )

    print("""Logs (check these first if VNC or Sunshine misbehaves next time):

  Master install log      /var/log/cloudgaming.log
                           (every command run by this script, full
                           stdout/stderr, plus copies of the service
                           logs below taken right after each service
                           started)

  VNC / Desktop session    ~/.vnc/*:1.log
                           ~/.config/tigervnc/*:1.log

  noVNC                    ~/novnc.log
  Moonlight Web            ~/moonlight-web.log
  Sunshine (startup)       ~/sunshine.log
  Sunshine (internal)      ~/.config/sunshine/sunshine.log
  Cloudflare tunnels       ~/novnc-cloudflare.log
                           ~/moonlight-web-cloudflare.log
                           ~/sunshine-cloudflare.log


Monitor:

~/cloud-monitor.py


========================================

""")


def run_monitor_foreground():

    out(
        "\n[MONITOR] Starting live dashboard "
        "(Ctrl+C to exit — services keep running in the background)\n"
    )

    time.sleep(1)

    # Replaces this process with the monitor, in the foreground,
    # attached to the current terminal — so it stays open and visible
    # instead of silently dying in a log file like the old nohup
    # version did. Runs directly as root now, no `su` needed.
    os.execvp(
        "python3",
        ["python3", f"{HOME}/cloud-monitor.py"]
    )


def main():

    check_root()

    record_system_info()

    choose_ui()

    check_region()

    update_system()

    install_base()

    install_steam()

    install_heroic()

    setup_vnc()

    disable_screen_lock()

    setup_novnc()

    install_cloudflared()


    start_cloudflare(
        "novnc",
        6001
    )


    setup_moonlight_web()


    start_cloudflare(
        "moonlight-web",
        8081
    )


    setup_sunshine()


    # Sunshine's web UI is HTTPS-only (self-signed cert), so the
    # tunnel has to point at https:// with TLS verification disabled —
    # pointing cloudflared at http:// here (as before) would just fail
    # to connect.
    start_cloudflare(
        "sunshine",
        47990,
        scheme="https",
        no_tls_verify=True
    )


    setup_wallpaper()

    urls = get_cloudflare_urls()

    create_monitor(urls)


    final_report(urls)


    # MUST run before the monitor takes over the terminal below
    moonlight_pair()

    # Final step: hand the terminal over to the live dashboard. This
    # never returns (Ctrl+C to stop watching) — the actual services
    # (VNC, noVNC, Sunshine, Moonlight Web, cloudflared tunnels) were
    # all started with nohup earlier and keep running independently.
    run_monitor_foreground()



if __name__=="__main__":

    try:
        main()

    except SystemExit:
        # run()'s fatal path already logged the command/reason and
        # calls sys.exit(1) itself -- re-raise as-is so we don't print
        # a second, less useful generic traceback on top of it.
        raise

    except KeyboardInterrupt:
        out("\n[STOP] Interrupted by user")

    except Exception:
        # Anything not already handled by run()'s try/except (e.g. a
        # bug in this script itself) still gets a full traceback saved
        # to /var/log/cloudgaming.log instead of just vanishing off the
        # screen when the terminal closes.
        out("\n====================")
        out("UNEXPECTED ERROR")
        out("====================")
        log(traceback.format_exc())
        print(traceback.format_exc())
        sys.exit(1)
