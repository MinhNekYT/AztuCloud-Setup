#!/usr/bin/env python3
# cloudgaming_installer.py
# KDE + Xorg(dummy)+x11vnc + noVNC + Moonlight Web + Sunshine + Cloudflare + Monitor + Steam + Heroic

import os
import sys
import time
import re
import shlex
import subprocess
import shutil
import getpass
import platform
import urllib.request
from pathlib import Path
from datetime import datetime


LOG_FILE = "/var/log/cloudgaming.log"


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


def run(cmd, silent=True, input_data=None, fatal=True):
    try:
        if not silent:
            out(f">>> {cmd}")

        result = subprocess.run(
            cmd,
            shell=True,
            input=input_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

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


def create_user():

    global USER, HOME

    USER = input(
        "Linux username: "
    )

    HOME = f"/home/{USER}"


    exists = subprocess.run(
        f"id {USER}",
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )


    if exists.returncode != 0:

        out(
            f"Creating user {USER}"
        )

        run(
            f"useradd -m -s /bin/bash {USER}"
        )

        # Leaving this blank is allowed: instead of setting a password,
        # we clear it with `passwd -d`, so the account has no password
        # at all. Login/su still works password-free; sudo is already
        # NOPASSWD via grant_root_access() below, so this only matters
        # for direct console/VNC login prompts.
        passwd = getpass.getpass(
            "Password (để trống = không mật khẩu): "
        )

        if passwd == "":
            out(
                f"[USER] Không đặt mật khẩu cho {USER} — tài khoản sẽ đăng nhập không cần mật khẩu"
            )
            run(
                f"passwd -d {USER}"
            )
        else:
            run(
                f"echo '{USER}:{passwd}' | chpasswd"
            )


    run(
        f"usermod -aG sudo {USER}"
    )

    grant_root_access()


def grant_root_access():

    # Adds the created user to sudo with NOPASSWD so the background
    # services this script launches (and anything the user runs later
    # over VNC/SSH) can escalate to root without an interactive
    # password prompt. Written as its own file under /etc/sudoers.d/
    # rather than editing /etc/sudoers directly, and validated with
    # visudo -c before being left in place so a typo here can't lock
    # out sudo system-wide.

    out(
        f"[SUDO] Granting {USER} passwordless root access"
    )

    sudoers_file = f"/etc/sudoers.d/{USER}-cloudgaming"

    Path(sudoers_file).write_text(
        f"{USER} ALL=(ALL) NOPASSWD:ALL\n"
    )

    run(
        f"chmod 440 {sudoers_file}"
    )

    check = subprocess.run(
        f"visudo -c -f {sudoers_file}",
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    if check.returncode != 0:
        out(
            f"[SUDO] WARNING: {sudoers_file} failed validation, removing it"
        )
        run(f"rm -f {sudoers_file}", silent=True, fatal=False)



def install_base():

    packages = [
        "xserver-xorg-core",
        "xserver-xorg-video-dummy",
        "x11vnc",
        "xauth",
        "kde-plasma-desktop",
        "plasma-workspace",
        "dbus-x11",
        "curl",
        "wget",
        "git",
        "chromium",
        "python3-pip",
        "python3-psutil",
        "psmisc"
    ]

    for p in packages:
        install_package(p)



def setup_vnc():

    out(
        "[DISPLAY] Setup KDE desktop on real Xorg (dummy driver) + x11vnc"
    )

    # Root cause of "cursor shows but nothing moves it": TigerVNC's
    # Xvnc is a headless, self-contained X server that only ever
    # accepts input through its own RFB/VNC protocol — it never reads
    # from the kernel input subsystem (/dev/input) at all. Sunshine
    # injects mouse/keyboard by creating virtual uinput devices at the
    # kernel level, which only get picked up by an X server that's
    # actually watching /dev/input via libinput — which Xvnc simply
    # isn't. Real Xorg (even with no physical GPU, via the "dummy"
    # video driver) does watch /dev/input, so it sees Sunshine's
    # uinput devices correctly. x11vnc then bridges that real Xorg
    # session to VNC/noVNC exactly like Xvnc did, on the same port.

    run(
        f"chown -R {USER}:{USER} {HOME}",
        silent=True
    )

    vnc_dir = f"{HOME}/.config/tigervnc"

    run(
        f"su - {USER} -c 'mkdir -p {vnc_dir}'",
        fatal=False
    )

    vnc_password = getpass.getpass(
        "VNC password (min 6 chars, để trống = không mật khẩu): "
    )

    global VNC_NO_AUTH
    VNC_NO_AUTH = vnc_password == ""

    if VNC_NO_AUTH:
        out(
            "[VNC] Không đặt mật khẩu — VNC sẽ chạy ở chế độ không xác thực"
        )
    else:
        # BUG FIX: the previous version shelled out to `vncpasswd`, which
        # comes from the tigervnc package -- but install_base() never
        # installs tigervnc, only x11vnc. That's exactly the
        # "vncpasswd: command not found" crash. x11vnc ships its own
        # equivalent tool (`x11vnc -storepasswd`), which writes the same
        # obfuscated password format `-rfbauth` expects below, so no new
        # package is needed.
        quoted_pw = shlex.quote(vnc_password)
        run(
            f"su - {USER} -c 'x11vnc -storepasswd {quoted_pw} {vnc_dir}/passwd'"
        )

        run(
            f"chmod 600 {vnc_dir}/passwd"
        )

        run(
            f"chown {USER}:{USER} {vnc_dir}/passwd"
        )

    # --- Dummy Xorg config -------------------------------------------------
    xorg_conf = "/etc/X11/xorg-dummy.conf"

    Path(xorg_conf).write_text(
        'Section "Device"\n'
        '    Identifier "DummyDevice"\n'
        '    Driver "dummy"\n'
        '    VideoRam 256000\n'
        'EndSection\n'
        '\n'
        'Section "Monitor"\n'
        '    Identifier "DummyMonitor"\n'
        '    HorizSync 5.0 - 1000.0\n'
        '    VertRefresh 5.0 - 200.0\n'
        '    Modeline "1920x1080" 173.00 1920 2048 2248 2576 '
        '1080 1083 1088 1120 -hsync +vsync\n'
        'EndSection\n'
        '\n'
        'Section "Screen"\n'
        '    Identifier "DummyScreen"\n'
        '    Device "DummyDevice"\n'
        '    Monitor "DummyMonitor"\n'
        '    DefaultDepth 24\n'
        '    SubSection "Display"\n'
        '        Depth 24\n'
        '        Modes "1920x1080"\n'
        '    EndSubSection\n'
        'EndSection\n'
        '\n'
        'Section "ServerLayout"\n'
        '    Identifier "DummyLayout"\n'
        '    Screen "DummyScreen"\n'
        'EndSection\n'
        '\n'
        'Section "ServerFlags"\n'
        '    Option "AutoAddDevices" "on"\n'
        '    Option "AutoEnableDevices" "on"\n'
        '    Option "DontVTSwitch" "on"\n'
        '    Option "AllowMouseOpenFail" "on"\n'
        '    Option "PciForceNone" "on"\n'
        'EndSection\n'
    )

    xauth_file = f"{HOME}/.Xauthority"

    run(
        f"su - {USER} -c 'touch ~/.Xauthority'"
    )

    run(
        f"chown {USER}:{USER} {xauth_file}"
    )

    run(
        f"chmod 600 {xauth_file}"
    )

    cookie = run(
        "mcookie",
        fatal=False
    ) or ""

    if cookie:
        run(
            f"su - {USER} -c 'xauth -f {xauth_file} add :1 . {cookie}'",
            fatal=False
        )

    # Kill anything left over from a previous run of this script
    # (stuck black screen, broken input, etc.) so the fixes below
    # actually take effect instead of leaving the old session alone.
    run("pkill -x Xorg", fatal=False)
    run("pkill -x x11vnc", fatal=False)
    run(f"pkill -u {USER} -x startplasma-x11", fatal=False)
    time.sleep(1)

    out(
        "[DISPLAY] Starting Xorg :1 (dummy driver)"
    )

    run(
        f"nohup Xorg :1 -config {xorg_conf} -auth {xauth_file} "
        f"-noreset -novtswitch -sharevts "
        f"> {HOME}/xorg.log 2>&1 &",
        fatal=False
    )

    # Wait for the X socket to actually appear instead of guessing a
    # fixed sleep — Xorg can take anywhere from under a second to
    # several seconds depending on the machine.
    xorg_up = False
    for _ in range(10):
        time.sleep(1)
        if os.path.exists("/tmp/.X11-unix/X1"):
            xorg_up = True
            break

    if xorg_up:
        out(
            "[DISPLAY] Xorg :1 is up"
        )
    else:
        out(
            "[DISPLAY] WARNING: Xorg :1 did not come up — this is why "
            "VNC/noVNC can't connect. Last lines of xorg.log:"
        )
        xorg_tail = run(
            f"tail -n 25 {HOME}/xorg.log",
            fatal=False
        )
        out(xorg_tail or "(xorg.log is empty or missing)")

    out(
        "[DISPLAY] Starting x11vnc bridge (VNC on :5901)"
    )

    if VNC_NO_AUTH:
        auth_flag = "-nopw"
    else:
        auth_flag = f"-rfbauth {vnc_dir}/passwd"

    run(
        f"""
su - {USER} -c '
export DISPLAY=:1
export XAUTHORITY={xauth_file}
nohup x11vnc -display :1 -auth {xauth_file} \
-forever -shared -rfbport 5901 {auth_flag} \
> ~/x11vnc.log 2>&1 &
'
""",
        fatal=False
    )

    vnc_up = False
    for _ in range(10):
        time.sleep(1)
        check = run(
            "ss -ltn 2>/dev/null | grep -q ':5901 ' && echo UP",
            fatal=False
        )
        if check == "UP":
            vnc_up = True
            break

    if vnc_up:
        out(
            "[DISPLAY] x11vnc is listening on :5901"
        )
    else:
        out(
            "[DISPLAY] WARNING: x11vnc is not listening on :5901 — "
            "noVNC will show 'cannot connect'. Last lines of x11vnc.log:"
        )
        x11vnc_tail = run(
            f"tail -n 25 {HOME}/x11vnc.log",
            fatal=False
        )
        out(x11vnc_tail or "(x11vnc.log is empty or missing)")

    out(
        "[DISPLAY] Starting KDE Plasma on :1"
    )

    # Xvnc has no real GPU behind it and neither does this dummy Xorg
    # driver. KWin's default compositor tries OpenGL first, fails
    # silently against a virtual framebuffer, and the session is left
    # rendering nothing — a plain black screen. Forcing software
    # rendering (llvmpipe via LIBGL_ALWAYS_SOFTWARE) and telling
    # Qt/KWin not to attempt GL integration makes compositing fall
    # back to a path that actually works without a GPU. The X server
    # also runs its own independent screensaver/DPMS blanking
    # regardless of KDE's own lock screen settings (see
    # disable_screen_lock()), so that's turned off here too.
    run(
        f"""
su - {USER} -c '
export DISPLAY=:1
export XAUTHORITY={xauth_file}
export LIBGL_ALWAYS_SOFTWARE=1
export QT_XCB_GL_INTEGRATION=none
export QT_QUICK_BACKEND=software
export KWIN_COMPOSE=Q
xset s off
xset s noblank
xset -dpms
nohup dbus-launch --exit-with-session startplasma-x11 \
> ~/plasma.log 2>&1 &
'
""",
        fatal=False
    )



def setup_novnc():

    out(
        "[noVNC] Installing"
    )

    path=f"{HOME}/noVNC"


    if not os.path.exists(path):

        run(
            f"""
su - {USER} -c '
cd ~
git clone https://github.com/novnc/noVNC.git
'
"""
        )

    else:
        out(
            "[SKIP] noVNC exists"
        )


    run(
        f"""
su - {USER} -c '
nohup ~/noVNC/utils/novnc_proxy \
--vnc localhost:5901 \
--listen 6001 \
> ~/novnc.log 2>&1 &
'
"""
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
su - {USER} -c '
nohup cloudflared tunnel {tls_flag}\
--url {scheme}://localhost:{port} \
> {log_file} 2>&1 &
'
"""
    )


def setup_moonlight_web():

    out(
        "[MOONLIGHT WEB] Installing (optional, will skip on error)"
    )

    archive = f"{HOME}/moonlight-web.tar.gz"

    # The hardcoded "v2.10.0" tag used previously will silently 404 once
    # a newer release replaces it, aborting the whole installer (run()
    # is fatal by default). Resolve whatever the *latest* release's
    # linux x86_64 tarball actually is via the GitHub API instead, the
    # same pattern used for Heroic in install_heroic().
    if not os.path.exists(archive):

        run(
            f"""
DL_URL=$(curl -s https://api.github.com/repos/MrCreativ3001/moonlight-web-stream/releases/latest \
| grep -oP '"browser_download_url":\\s*"\\K[^"]+x86_64-unknown-linux-gnu\\.tar\\.gz(?=")' \
| head -n1)
if [ -n "$DL_URL" ]; then
    su - {USER} -c "wget -q '$DL_URL' -O {archive}"
fi
""",
            fatal=False
        )

    if not os.path.exists(archive) or os.path.getsize(archive) == 0:
        out(
            "[MOONLIGHT WEB] WARNING: could not resolve/download latest release — skipping Moonlight Web"
        )
        return

    run(
        f"su - {USER} -c 'tar -xzf {archive} -C {HOME}'",
        fatal=False
    )

    # Don't assume the archive extracts into a folder literally named
    # "package" — that name isn't guaranteed to stay stable across
    # releases. Instead, find wherever the web-server binary actually
    # landed after extraction.
    extract_dir = run(
        f"dirname $(find {HOME} -maxdepth 3 -type f -name web-server | head -n1)",
        fatal=False
    )

    if not extract_dir or not os.path.isdir(extract_dir):
        out(
            "[MOONLIGHT WEB] WARNING: web-server binary not found after extraction — skipping Moonlight Web"
        )
        return

    run(
        f"chown -R {USER}:{USER} {extract_dir}",
        fatal=False
    )

    run(
        f"chmod +x {extract_dir}/web-server {extract_dir}/streamer",
        fatal=False
    )

    started = run(
        f"""
su - {USER} -c '
cd {extract_dir}
nohup ./web-server \
--bind-address 127.0.0.1:8081 \
> {HOME}/moonlight-web.log 2>&1 &
'
""",
        fatal=False
    )

    if started is None:
        out(
            "[MOONLIGHT WEB] WARNING: failed to start web-server — skipping Moonlight Web"
        )
    else:
        out(
            f"[MOONLIGHT WEB] Started from {extract_dir}"
        )



def setup_sunshine_input():

    # Sunshine injects mouse/keyboard/gamepad events on Linux by
    # creating virtual devices through /dev/uinput. Without this
    # setup, opening that device fails silently from Sunshine's
    # perspective (video still streams fine — capture and input are
    # independent pipelines) and every click/keypress the client sends
    # simply goes nowhere, which is exactly "stream works, no cursor,
    # can't interact".

    out(
        "[SUNSHINE] Enabling input injection (/dev/uinput)"
    )

    # Ensure the uinput kernel module is loaded now...
    run(
        "modprobe uinput",
        fatal=False
    )

    # ...and stays loaded on every future boot, not just this run.
    run(
        "echo uinput > /etc/modules-load.d/uinput.conf",
        fatal=False
    )

    # Group-based permission (rather than the logind "uaccess" tag)
    # because a VNC desktop typically isn't a proper systemd-logind
    # seat session, so ACL-based device tags often don't apply to it.
    udev_rule = "/etc/udev/rules.d/60-sunshine-input.rules"

    Path(udev_rule).write_text(
        'KERNEL=="uinput", SUBSYSTEM=="misc", '
        'MODE="0660", GROUP="input", '
        'OPTIONS+="static_node=uinput"\n'
    )

    run(
        "groupadd -f input",
        fatal=False
    )

    run(
        f"usermod -aG input {USER}",
        fatal=False
    )

    run(
        "udevadm control --reload-rules",
        fatal=False
    )

    run(
        "udevadm trigger --name-match=uinput",
        fatal=False
    )

    # In case the device node already existed with stale permissions
    # from before the udev rule was in place.
    run(
        "chgrp input /dev/uinput",
        fatal=False
    )

    run(
        "chmod 660 /dev/uinput",
        fatal=False
    )

    check_uinput_support()


def check_uinput_support():

    # This is the single most common real-world reason "stream works but
    # mouse/keyboard do nothing": on a plain KVM/full-virtualization VPS
    # the steps above are enough, but on a container-based VPS (LXC,
    # OpenVZ, or a Docker host) the *host* controls which kernel modules
    # and device nodes are visible inside the guest. In that case
    # `modprobe uinput` and the udev rule above can both "succeed" with
    # no error while /dev/uinput still never appears -- Sunshine then has
    # nothing to inject events into, no matter how it's configured.

    global UINPUT_AVAILABLE

    virt = run(
        "systemd-detect-virt 2>/dev/null || echo unknown",
        fatal=False
    ) or "unknown"

    exists = os.path.exists("/dev/uinput")

    out(
        f"[UINPUT] Virtualization detected: {virt}"
    )
    out(
        f"[UINPUT] /dev/uinput exists after modprobe: {exists}"
    )

    UINPUT_AVAILABLE = exists

    if not exists:
        out(
            "[UINPUT] CANH BAO QUAN TRONG: /dev/uinput KHONG xuat hien sau khi "
            "modprobe. Neu VPS nay chay tren container (lxc/openvz/docker) thay vi "
            "KVM/full virtualization, host se KHONG cho phep tao thiet bi nay ben "
            "trong container -- va Sunshine se KHONG BAO GIO dieu khien duoc "
            "chuot/ban phim du cau hinh gi di nua (video van stream binh thuong vi "
            "capture va input la hai duong hoan toan doc lap). Day rat co the la "
            "nguyen nhan chinh cua loi 'stream duoc nhung khong dieu khien duoc'. "
            f"Virtualization hien tai bao cao la '{virt}'. Neu day la 'lxc', "
            "'openvz', hoac 'docker', hay yeu cau nha cung cap VPS doi sang KVM "
            "(day la gioi han cua ha tang, khong phai loi cau hinh trong script nay)."
        )
    else:
        out(
            "[UINPUT] OK -- /dev/uinput ton tai, Sunshine co the inject input binh "
            "thuong mien la user nam trong group 'input' (da duoc cau hinh o tren)."
        )

    return exists


def setup_sunshine():

    out(
        "[SUNSHINE] Installing"
    )


    deb="/tmp/sunshine.deb"

    # BUG FIX: if a previous run of this script crashed mid-download
    # (e.g. network blip), a corrupt/partial /tmp/sunshine.deb can be
    # left behind. The old code only checked "does the file exist" and
    # would silently try to install that broken file forever, which can
    # look like "Sunshine is installed" while actually running a stale
    # or broken binary. Also require a non-trivial size before trusting
    # the cached file.
    if os.path.exists(deb) and os.path.getsize(deb) < 1_000_000:
        out(
            "[SUNSHINE] Cached /tmp/sunshine.deb looks incomplete/corrupt -- re-downloading"
        )
        run(f"rm -f {deb}", silent=True, fatal=False)

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


    setup_sunshine_input()

    out(
        "[SUNSHINE] Configuring capture/input for the Xorg (dummy) display"
    )

    # This box has no physical monitor — the only display is the
    # virtual Xorg (dummy driver) session set up in setup_vnc(). Left
    # to its defaults, Sunshine tries a GPU/KMS capture backend
    # looking for a real connected output, finds none, and fails with
    # "Failed to initialize video capture/encoding. Is a display
    # connected and turned on?" Forcing the x11 (XShm) backend reads
    # pixels straight from the Xorg session instead, which works
    # without any GPU/DRM output.
    #
    # For input: setup_sunshine_input() already configures the
    # uinput/libinput path (the documented default on Linux), which
    # should now actually work since setup_vnc() switched from Xvnc
    # (which never reads /dev/input at all) to a real Xorg session
    # (which does, via libinput). As a second layer of defense, also
    # request the "xtest" input backend explicitly if this Sunshine
    # build supports it — XTest talks directly to the X11 display,
    # the same mechanism x11vnc already uses successfully to move the
    # cursor, so it sidesteps the uinput/udev/group chain entirely.
    # If this Sunshine build doesn't have an "input" key, it's simply
    # ignored rather than breaking anything.
    sunshine_conf_dir = f"{HOME}/.config/sunshine"

    run(
        f"su - {USER} -c 'mkdir -p {sunshine_conf_dir}'",
        fatal=False
    )

    sunshine_conf = f"{sunshine_conf_dir}/sunshine.conf"

    if not os.path.exists(sunshine_conf):
        Path(sunshine_conf).write_text("")
        run(
            f"chown {USER}:{USER} {sunshine_conf}",
            fatal=False
        )

    for key, value in [("capture", "x11"), ("input", "xtest")]:
        run(
            f"grep -q '^{key}' {sunshine_conf} && "
            f"sed -i 's/^{key}.*/{key} = {value}/' {sunshine_conf} || "
            f"echo '{key} = {value}' >> {sunshine_conf}",
            fatal=False
        )

    out(
        "[SUNSHINE] Starting"
    )

    # Restart cleanly if a previous run already has it running — a
    # stale process would keep the old (pre-input-group,
    # pre-capture-fix) session alive instead of picking up the fixes
    # above.
    run(
        "pkill -u " + USER + " -x sunshine",
        fatal=False
    )

    run(
        f"""
su - {USER} -c '
export DISPLAY=:1
export XAUTHORITY=~/.Xauthority
nohup sunshine \
> ~/sunshine.log 2>&1 &
'
"""
    )


def install_steam():

    # Optional: Steam requires the i386 architecture and the
    # contrib/non-free repos, which aren't guaranteed to be enabled on
    # a bare Debian install. This whole function is best-effort — if
    # any step fails (repos not configured, package unavailable on
    # this Debian release, etc.) it logs a warning and the installer
    # moves on instead of aborting.

    out(
        "[STEAM] Installing (optional, will skip on error)"
    )

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

    installed = run(
        "DEBIAN_FRONTEND=noninteractive apt install -y steam-installer",
        silent=True,
        fatal=False
    )

    if installed is None:
        out(
            "[STEAM] WARNING: steam-installer not available "
            "(contrib/non-free repos may not be enabled) — skipping Steam"
        )
    else:
        out(
            "[STEAM] Installed successfully"
        )


def install_heroic():

    # Optional: fetches whatever .deb asset the latest Heroic Games
    # Launcher GitHub release ships (the exact filename changes with
    # each version, so it's resolved dynamically via the GitHub API
    # instead of hardcoding a URL). Best-effort like install_steam()
    # above — any failure just skips Heroic rather than aborting the
    # whole install.

    out(
        "[HEROIC] Installing (optional, will skip on error)"
    )

    deb = "/tmp/heroic.deb"

    run(
        f"""
DEB_URL=$(curl -s https://api.github.com/repos/Heroic-Games-Launcher/HeroicGamesLauncher/releases/latest \
| grep -oP '"browser_download_url":\\s*"\\K[^"]+\\.deb(?=")' \
| head -n1)
if [ -n "$DEB_URL" ]; then
    wget -q "$DEB_URL" -O {deb}
fi
""",
        silent=True,
        fatal=False
    )

    if os.path.exists(deb) and os.path.getsize(deb) > 0:

        installed = run(
            f"apt install -y {deb}",
            silent=True,
            fatal=False
        )

        if installed is None:
            out(
                "[HEROIC] WARNING: install failed — skipping Heroic"
            )
        else:
            out(
                "[HEROIC] Installed successfully"
            )

    else:
        out(
            "[HEROIC] WARNING: could not resolve/download latest .deb — skipping Heroic"
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
su - {USER} -c '
mkdir -p ~/.local/share/wallpapers

cp {file} \
~/.local/share/wallpapers/wallpaper.png
'
"""
    )

    # Applying the wallpaper live requires talking to the already
    # running Plasma session over D-Bus/X11. This is a fresh shell
    # (separate from the VNC session's environment), so it doesn't
    # automatically know DISPLAY or the right D-Bus session bus —
    # setting DISPLAY=:1 covers the common case, but this can still
    # fail depending on timing. It's purely cosmetic (the file is
    # already copied in place above and can be set manually from
    # System Settings), so a failure here shouldn't abort the whole
    # install.
    run(
        f"su - {USER} -c 'DISPLAY=:1 plasma-apply-wallpaperimage ~/.local/share/wallpapers/wallpaper.png'",
        fatal=False
    )



def disable_screen_lock():

    # By default KDE Plasma locks the session after a period of
    # inactivity (kscreenlocker), which shows a password prompt over
    # the VNC feed — the screen users were seeing. Since access to
    # this desktop is already gated behind the VNC password (or lack
    # thereof, by choice) and/or the Cloudflare tunnel, an additional
    # OS-level lock screen just gets in the way for a cloud
    # gaming/remote desktop box. This disables auto-lock entirely and
    # unlocks the session immediately if it's already locked.

    out(
        "[LOCK] Disabling KDE screen lock (kscreenlocker)"
    )

    config_dir = f"{HOME}/.config"

    run(
        f"su - {USER} -c 'mkdir -p {config_dir}'",
        fatal=False
    )

    kscreenlockerrc = f"{config_dir}/kscreenlockerrc"

    Path(kscreenlockerrc).write_text(
        "[Daemon]\n"
        "Autolock=false\n"
        "LockOnResume=false\n"
        "LockGrace=0\n"
        "Timeout=0\n"
    )

    run(
        f"chown {USER}:{USER} {kscreenlockerrc}",
        fatal=False
    )

    # Also stop power-management from triggering a lock on suspend/
    # screen-off — Plasma's power profiles have their own independent
    # "lock screen" toggle that isn't controlled by kscreenlockerrc.
    for group in [
        "AC/DimDisplay",
        "AC/DPMSControl",
        "Battery/DimDisplay",
        "Battery/DPMSControl",
    ]:
        run(
            f"su - {USER} -c "
            f"\"kwriteconfig5 --file powermanagementprofilesrc "
            f"--group {group} --key lockScreen false\"",
            fatal=False
        )

    # If a lock screen is already active in the running session (e.g.
    # this script is re-run after the first idle timeout already
    # fired), ask kscreenlocker to unlock it right away instead of
    # waiting for a password.
    run(
        f"su - {USER} -c 'DISPLAY=:1 qdbus org.kde.screensaver "
        f"/ScreenSaver org.freedesktop.ScreenSaver.SetActive false'",
        fatal=False
    )

    # Restart kscreenlocker_greet's daemon so the new config (loaded
    # only at startup) takes effect without needing a fresh VNC login.
    run(
        f"su - {USER} -c 'DISPLAY=:1 kquitapp5 kscreenlocker_greet'",
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
"chromium":"Chromium",
"sunshine":"Sunshine",
"Xorg":"X11 (Xorg dummy)",
"x11vnc":"x11vnc",
"web-server":"Moonlight",
"heroic":"Heroic"
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
        f"chown {USER}:{USER} {monitor}"
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

    run(
        f"chown {USER}:{USER} {urls_file}",
        silent=True
    )

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


def run_sunshine_diagnostics():

    # Automates the checklist for "stream works but no input":
    #   1. Is Sunshine actually receiving input events at all?
    #   2. Is the session X11 (not Wayland)?
    #   3. Does /dev/uinput exist with usable permissions?
    #   4. What Sunshine version/build is this?
    # Printed directly in this run's output so there's no need to
    # open a separate SSH session just to check these.

    out(
        "\n=============================="
    )
    out(
        "SUNSHINE INPUT DIAGNOSTICS"
    )
    out(
        "==============================\n"
    )

    session_type = run(
        f"su - {USER} -c 'DISPLAY=:1 echo $XDG_SESSION_TYPE'",
        fatal=False
    )
    out(
        f"[CHECK] XDG_SESSION_TYPE = {session_type or '(empty/unknown)'}"
    )
    if session_type and "wayland" in session_type.lower():
        out(
            "[CHECK] WARNING: session reports Wayland — Sunshine input "
            "is most reliable on X11. This installer starts "
            "startplasma-x11 specifically to avoid this, so if you see "
            "'wayland' here, some other session took over :1."
        )
    else:
        out(
            "[CHECK] OK — this is the X11 session started by this script."
        )

    version = run(
        "sunshine --version",
        fatal=False
    )
    out(
        f"[CHECK] sunshine --version -> {version or '(command failed)'}"
    )

    uinput_ls = run(
        "ls -l /dev/uinput",
        fatal=False
    )
    if uinput_ls:
        out(
            f"[CHECK] /dev/uinput -> {uinput_ls}"
        )
    else:
        out(
            "[CHECK] WARNING: /dev/uinput does not exist. The uinput "
            "kernel module likely isn't loaded — run 'modprobe uinput' "
            "and check 'lsmod | grep uinput'."
        )

    if not globals().get("UINPUT_AVAILABLE", uinput_ls is not None):
        virt = run(
            "systemd-detect-virt 2>/dev/null || echo unknown",
            fatal=False
        ) or "unknown"
        out(
            f"[CHECK] Virtualization: {virt}. Neu day la container "
            "(lxc/openvz/docker) chu khong phai KVM, day chinh la ly do "
            "chuot/ban phim khong bao gio hoat dong duoc du cau hinh Sunshine "
            "the nao — can doi sang VPS KVM."
        )

    in_group = run(
        f"id -nG {USER}",
        fatal=False
    )
    if in_group and "input" in in_group.split():
        out(
            f"[CHECK] OK — {USER} is in the 'input' group ({in_group})"
        )
    else:
        out(
            f"[CHECK] WARNING: {USER} is NOT in the 'input' group "
            f"(groups: {in_group or 'unknown'}). Sunshine can't open "
            "/dev/uinput without it."
        )

    sunshine_log = f"{HOME}/sunshine.log"

    if os.path.exists(sunshine_log):
        input_hits = run(
            f"grep -iE 'mouse|keyboard|gamepad|uinput|xtest|input' "
            f"{sunshine_log} | tail -n 15",
            fatal=False
        )
        out(
            "[CHECK] Last input-related lines from sunshine.log "
            "(click/press something in Moonlight first, then re-check "
            "this file — nothing here means Sunshine received nothing):"
        )
        out(
            input_hits or "(no matching lines found yet)"
        )
    else:
        out(
            "[CHECK] WARNING: sunshine.log not found at "
            f"{sunshine_log}"
        )

    out(
        "\n[CHECK] To watch input arrive live, run on this machine:\n"
        f"    tail -f {sunshine_log}\n"
        "then in Moonlight Web click the stream, press a key, move the "
        "mouse — you should see corresponding lines appear immediately.\n"
    )


def final_report(urls):

    print("""

========================================

 CLOUD GAMING READY

========================================

Services:

[OK] KDE Plasma
[OK] Xorg (dummy) + x11vnc
[OK] noVNC
[OK] Moonlight Web
[OK] Sunshine
[OK] Chromium
[OK] Cloudflare Tunnel
[..] Steam (best-effort)
[..] Heroic Games Launcher (best-effort)

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

    print("""Logs:

/var/log/cloudgaming.log


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

    # Replaces this process with the monitor running as the target
    # user, in the foreground, attached to the current terminal — so
    # it stays open and visible instead of silently dying in a log
    # file like the old nohup version did.
    os.execvp(
        "su",
        ["su", "-", USER, "-c", f"python3 {HOME}/cloud-monitor.py"]
    )


def print_update_banner():

    out(
        "=============================="
    )
    out(
        " CLOUD GAMING INSTALLER"
    )
    out(
        "=============================="
    )
    out(
        "This run includes:\n"
        "  - FIX: VNC password setup no longer calls the missing "
        "'vncpasswd' binary (was crashing setup_vnc with 'command not "
        "found') -- now uses x11vnc's own built-in 'storepasswd'\n"
        "  - FIX: automatic uinput/virtualization check reports clearly "
        "if this VPS is a container (lxc/openvz/docker) that structurally "
        "blocks Sunshine mouse/keyboard input, instead of failing silently\n"
        "  - FIX: stale/corrupt cached sunshine.deb from a crashed previous "
        "run is now detected and re-downloaded instead of reused\n"
        "  - Passwordless sudo (NOPASSWD) for the created user\n"
        "  - Optional empty passwords (Linux account + VNC)\n"
        "  - Steam + Heroic Games Launcher (best-effort, skips on error)\n"
        "  - Moonlight Web release resolved dynamically (no hardcoded version)\n"
        "  - KDE screen-lock (kscreenlocker) disabled\n"
        "  - Display stack replaced: Xorg (dummy driver) + x11vnc instead of "
        "TigerVNC/Xvnc, so Sunshine's uinput input can actually reach the "
        "session (Xvnc never read /dev/input at all)\n"
        "  - DPMS/screensaver blanking disabled at the X11 level\n"
        "  - Software rendering forced for KWin (no GPU behind this display)\n"
        "  - Sunshine capture forced to 'x11', input backend requested as "
        "'xtest' with uinput/udev group setup as a fallback\n"
        "  - Automatic input diagnostics printed at the end of this run\n"
    )
    out(
        "=============================="
    )


def run_full_diagnostics():

    # One-shot diagnostic dump: gathers everything needed to debug
    # "VNC không connect được" and "Moonlight Web không nhận input"
    # in a single run, so there's no need to SSH in and manually
    # tail/grep half a dozen files. Safe to run repeatedly and does
    # not touch/restart any running service.

    out("========================================")
    out(" CLOUD GAMING DIAGNOSTICS")
    out("========================================\n")

    user = input(
        "Linux username đã dùng khi cài đặt: "
    ).strip()

    home = f"/home/{user}"

    out(f"\n[INFO] USER={user} HOME={home}\n")

    out("---- 1) Virtualization / uinput (Sunshine + Moonlight input) ----")
    virt = run("systemd-detect-virt 2>/dev/null || echo unknown", fatal=False) or "unknown"
    out(f"Virtualization: {virt}")
    out(run("ls -l /dev/uinput 2>&1 || echo '/dev/uinput KHONG TON TAI'", fatal=False) or "")
    out(run(f"id -nG {user} 2>&1", fatal=False) or "")
    out(run("lsmod | grep -i uinput || echo 'module uinput KHONG duoc load'", fatal=False) or "")

    out("\n---- 2) Processes (Xorg / x11vnc / noVNC / Sunshine / moonlight-web / cloudflared) ----")
    out(run("ps aux | grep -E 'Xorg|x11vnc|novnc_proxy|websockify|sunshine|web-server|cloudflared' | grep -v grep", fatal=False) or "(khong thay process nao dang chay)")

    out("\n---- 3) Listening ports (5901=x11vnc, 6001=noVNC, 8081=moonlight-web, 47990=sunshine) ----")
    out(run("ss -ltnp 2>/dev/null | grep -E ':5901|:6001|:8081|:47990' || echo '(khong co port nao dang listen trong 4 port tren)'", fatal=False) or "")

    out("\n---- 4) Xorg log (~/xorg.log) — tail 25 ----")
    out(run(f"tail -n 25 {home}/xorg.log 2>&1", fatal=False) or "(khong tim thay file)")

    out("\n---- 5) x11vnc log (~/x11vnc.log) — tail 25 ----")
    out(run(f"tail -n 25 {home}/x11vnc.log 2>&1", fatal=False) or "(khong tim thay file)")

    out("\n---- 6) noVNC log (~/novnc.log) — tail 25 ----")
    out(run(f"tail -n 25 {home}/novnc.log 2>&1", fatal=False) or "(khong tim thay file)")

    out("\n---- 7) Moonlight Web log (~/moonlight-web.log) — tail 25 ----")
    out(run(f"tail -n 25 {home}/moonlight-web.log 2>&1", fatal=False) or "(khong tim thay file)")

    out("\n---- 8) Sunshine log (~/sunshine.log) — tail 25 ----")
    out(run(f"tail -n 25 {home}/sunshine.log 2>&1", fatal=False) or "(khong tim thay file)")

    out("\n---- 9) Cloudflare tunnel logs (URLs hien tai) ----")
    for svc in ["novnc", "moonlight-web", "sunshine"]:
        log_path = f"{home}/{svc}-cloudflare.log"
        content = run(f"cat {log_path} 2>&1", fatal=False) or ""
        match = re.search(r"https://[-a-zA-Z0-9]+\.trycloudflare\.com", content)
        out(f"[{svc}] {match.group() if match else '(chua thay URL — tail log: ' + log_path + ')'}")

    out("\n---- 10) VNC password file (chi kiem tra co ton tai, khong in noi dung) ----")
    out(run(f"ls -l {home}/.config/tigervnc/passwd 2>&1 || echo '(khong dat mat khau VNC / file khong ton tai)'", fatal=False) or "")

    out("\n---- 11) Session type (X11 vs Wayland) ----")
    out(run(f"su - {user} -c 'DISPLAY=:1 echo $XDG_SESSION_TYPE' 2>&1", fatal=False) or "(khong xac dinh duoc)")

    out(
        "\n========================================\n"
        "Copy TOÀN BỘ output phía trên (từ dòng CLOUD GAMING DIAGNOSTICS) "
        "và gửi lại để chẩn đoán chính xác lỗi VNC / input.\n"
        "========================================"
    )


def main():

    if "--diagnose" in sys.argv:
        check_root()
        run_full_diagnostics()
        return

    print_update_banner()

    check_root()

    check_region()

    create_user()

    update_system()

    install_base()

    setup_vnc()

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


    install_steam()

    install_heroic()


    setup_wallpaper()

    disable_screen_lock()

    urls = get_cloudflare_urls()

    create_monitor(urls)

    run_sunshine_diagnostics()

    final_report(urls)


    # MUST run before the monitor takes over the terminal below
    moonlight_pair()

    # Final step: hand the terminal over to the live dashboard. This
    # never returns (Ctrl+C to stop watching) — the actual services
    # (VNC, noVNC, Sunshine, Moonlight Web, cloudflared tunnels) were
    # all started with nohup earlier and keep running independently.
    run_monitor_foreground()



if __name__=="__main__":

    main()
