import os
import time
import subprocess
import textwrap

ps1_code = textwrap.dedent(r'''
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class KeepAlive {
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern uint SetThreadExecutionState(uint esFlags);
}
"@
$form = New-Object System.Windows.Forms.Form
$form.Text = "AFK MODE"
$form.Size = New-Object System.Drawing.Size(300,150)
$form.StartPosition = "CenterScreen"
$form.TopMost = $true
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.BackColor = [System.Drawing.Color]::FromArgb(25,25,25)
$label = New-Object System.Windows.Forms.Label
$label.Text = "AFK MODE"
$label.ForeColor = [System.Drawing.Color]::LimeGreen
$label.Font = New-Object System.Drawing.Font("Segoe UI",24,[System.Drawing.FontStyle]::Bold)
$label.AutoSize = $true
$label.Dock = "Fill"
$label.TextAlign = "MiddleCenter"
$form.Controls.Add($label)
$job = Start-Job {
    Add-Type @"
using System;
using System.Runtime.InteropServices;
public class KeepAlive {
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern uint SetThreadExecutionState(uint esFlags);
}
"@
    while ($true) {
        [KeepAlive]::SetThreadExecutionState([uint32]0x80000002) | Out-Null
        Start-Sleep -Seconds 60
    }
}
$form.Add_FormClosing({
    Stop-Job $job -ErrorAction SilentlyContinue
    Remove-Job $job -ErrorAction SilentlyContinue
    [KeepAlive]::SetThreadExecutionState([uint32]0x80000000) | Out-Null
})
[System.Windows.Forms.Application]::Run($form)
''')

ps1_path = r"C:\keepalive.ps1"
created = False
try:
    with open(ps1_path, "w", encoding="utf-8") as f:
        f.write(ps1_code)
    print(f"[+] Đã tạo {ps1_path}")
    created = True
except OSError as e:
    print(f"[-] Không thể tạo {ps1_path}: {e}")

if created:
    creation_flags = 0
    if os.name == "nt":
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    subprocess.Popen(
        ["powershell", "-ExecutionPolicy", "Bypass", "-File", ps1_path],
        creationflags=creation_flags
    )

start_time = time.time()
while True:
    elapsed = int(time.time() - start_time)
    h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
    os.system("cls" if os.name == "nt" else "clear")
    print("==== AFK MODE ĐANG HOẠT ĐỘNG ====")
    print(f"Thời gian hoạt động: {h:02d}:{m:02d}:{s:02d}")
    print("(Đóng cửa sổ này để dừng)")
    time.sleep(1)