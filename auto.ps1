#===============================================
# Script Cài Đặt NVIDIA Driver & Các Thành Phần Khác
#===============================================
$ErrorActionPreference = "Stop"

# --- Kiểm tra quyền Quản trị viên ---
Write-Host "Đang kiểm tra quyền Quản trị viên..." -ForegroundColor Cyan

$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
$isAdmin = $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "        LỖI: THIẾU QUYỀN ADMIN" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "Script này YÊU CẦU quyền Quản trị viên để chạy." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Vui lòng:" -ForegroundColor Cyan
    Write-Host "  1. Nhấp chuột phải vào PowerShell" -ForegroundColor White
    Write-Host "  2. Chọn 'Chạy với tư cách quản trị viên'" -ForegroundColor White
    Write-Host "  3. Chạy lại script này" -ForegroundColor White
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Red
    Exit 1
}

Write-Host "Đã xác nhận quyền Quản trị viên. Tiếp tục..." -ForegroundColor Green
Write-Host ""

# --- Tải và cài đặt WinRAR ---
Write-Host "Bước 1: Tải và cài đặt WinRAR..." -ForegroundColor Cyan

$WinRarUrl = "https://www.win-rar.com/fileadmin/winrar-versions/winrar/winrar-x64-723.exe"
$WinRarPath = Join-Path -Path $env:TEMP -ChildPath "winrar-x64-723.exe"

try {
    Write-Host "Tải xuống WinRAR từ: $WinRarUrl" -ForegroundColor Gray
    Invoke-WebRequest -Uri $WinRarUrl -OutFile $WinRarPath -UseBasicParsing
    Write-Host "Tải xuống WinRAR hoàn tất." -ForegroundColor Green
    
    Write-Host "Cài đặt WinRAR..." -ForegroundColor Gray
    Start-Process -FilePath $WinRarPath -ArgumentList "/S" -Wait -Verb RunAs
    Write-Host "Cài đặt WinRAR hoàn tất." -ForegroundColor Green
    
    Remove-Item -Path $WinRarPath -Force
} catch {
    Write-Warning "Lỗi khi tải hoặc cài đặt WinRAR: $_"
}

# --- Tải và cài đặt DirectX Jun2010 ---
Write-Host "Bước 2: Tải và cài đặt DirectX Jun2010..." -ForegroundColor Cyan

$DirectXUrl = "https://download.microsoft.com/download/8/4/a/84a35bf1-dafe-4ae8-82af-ad2ae20b6b14/directx_Jun2010_redist.exe"
$DirectXPath = Join-Path -Path $env:TEMP -ChildPath "directx_Jun2010_redist.exe"
$DX11Dir = Join-Path -Path $env:TEMP -ChildPath "DX11"

try {
    # Tạo thư mục DX11
    New-Item -ItemType Directory -Path $DX11Dir -Force
    
    Write-Host "Tải xuống DirectX Jun2010 từ: $DirectXUrl" -ForegroundColor Gray
    Invoke-WebRequest -Uri $DirectXUrl -OutFile $DirectXPath -UseBasicParsing
    Write-Host "Tải xuống DirectX Jun2010 hoàn tất." -ForegroundColor Green
    
    Write-Host "Sao chép file DirectX vào thư mục DX11..." -ForegroundColor Gray
    Copy-Item -Path $DirectXPath -Destination $DX11Dir -Force
    
    # Di chuyển đến thư mục DX11 và chạy DXsetup
    Set-Location -Path $DX11Dir
    Write-Host "Chạy DXsetup từ thư mục DX11..." -ForegroundColor Gray
    $dxSetupPath = Join-Path -Path $DX11Dir -ChildPath "DXsetup.exe"
    Start-Process -FilePath $dxSetupPath -ArgumentList "/silent" -Wait
    Write-Host "Cài đặt DirectX Jun2010 hoàn tất." -ForegroundColor Green
    
    Set-Location -Path $env:TEMP
    Remove-Item -Path $DirectXPath -Force
} catch {
    Write-Warning "Lỗi khi tải hoặc cài đặt DirectX Jun2010: $_"
}

# --- Tải và cài đặt Visual C++ Redistributable ---
Write-Host "Bước 3: Tải và cài đặt Visual C++ Redistributable..." -ForegroundColor Cyan

$VCRedistUrl = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
$VCRedistPath = Join-Path -Path $env:TEMP -ChildPath "vc_redist.x64.exe"

try {
    Write-Host "Tải xuống Visual C++ Redistributable từ: $VCRedistUrl" -ForegroundColor Gray
    Invoke-WebRequest -Uri $VCRedistUrl -OutFile $VCRedistPath -UseBasicParsing
    Write-Host "Tải xuống Visual C++ Redistributable hoàn tất." -ForegroundColor Green
    
    Write-Host "Cài đặt Visual C++ Redistributable..." -ForegroundColor Gray
    Start-Process -FilePath $VCRedistPath -ArgumentList "/install", "/quiet", "/norestart" -Wait -Verb RunAs
    Write-Host "Cài đặt Visual C++ Redistributable hoàn tất." -ForegroundColor Green
    
    Remove-Item -Path $VCRedistPath -Force
} catch {
    Write-Warning "Lỗi khi tải hoặc cài đặt Visual C++ Redistributable: $_"
}

# --- Tải và đặt wallpaper cố định ---
Write-Host "Bước 4: Tải và đặt wallpaper..." -ForegroundColor Cyan

$WallpaperUrl = "https://github.com/MinhNekYT/AztuCloud-Setup/releases/download/wallpaper/wallpaper.jpg"
$wallpaperPath = "C:\wallpaper.jpg"

try {
    Write-Host "Đang tải wallpaper: $WallpaperUrl" -ForegroundColor Gray
    
    # Tải xuống wallpaper
    Invoke-WebRequest -Uri $WallpaperUrl -OutFile $wallpaperPath -UseBasicParsing
    Write-Host "Tải xuống wallpaper hoàn tất." -ForegroundColor Green
    
    # Sử dụng registry để đặt wallpaper
    $regPath = "HKCU:\Control Panel\Desktop"
    Set-ItemProperty -Path $regPath -Name Wallpaper -Value $wallpaperPath
    Set-ItemProperty -Path $regPath -Name WallpaperStyle -Value 2  # 2 = Stretch
    Set-ItemProperty -Path $regPath -Name TileWallpaper -Value 0  # 0 = Don't tile
    
    # Sử dụng API để cập nhật wallpaper ngay lập tức
    $sig = @"
[DllImport("user32.dll", SetLastError = true)]
public static extern int SystemParametersInfo(int uAction, int uParam, string lpvParam, int fuWinIni);
"@
    
    $SPI_SETDESKWALLPAPER = 20
    $SPIF_UPDATEINIFILE = 0x01
    $SPIF_SENDCHANGE = 0x02
    
    $setWallpaper = Add-Type -MemberDefinition $sig -Name "Win32" -Namespace "Win32" -PassThru
    $setWallpaper::SystemParametersInfo($SPI_SETDESKWALLPAPER, 0, $wallpaperPath, ($SPIF_UPDATEINIFILE -bor $SPIF_SENDCHANGE))
    
    Write-Host "Đã đặt wallpaper thành công." -ForegroundColor Green
} catch {
    Write-Warning "Lỗi khi tải hoặc đặt wallpaper: $_"
}

# --- Tắt tất cả các cổng Windows ---
Write-Host "Bước 5: Tắt tất cả các cổng Windows..." -ForegroundColor Cyan

try {
    Write-Host "Tắt tất cả các cổng Windows (firewall)..." -ForegroundColor Gray
    netsh advfirewall set allprofiles state off
    Write-Host "Đã tắt tất cả các cổng Windows." -ForegroundColor Green
} catch {
    Write-Warning "Lỗi khi tắt cổng Windows: $_"
}

# --- Tắt Windows Defender ---
Write-Host "Bước 6: Tắt Windows Defender..." -ForegroundColor Cyan

try {
    Write-Host "Tắt Windows Defender..." -ForegroundColor Gray
    # Tắt Windows Defender Service
    Stop-Service -Name "Windows Defender Service" -Force -ErrorAction SilentlyContinue
    Set-Service -Name "Windows Defender Service" -StartupType Disabled
    
    # Tắt Windows Defender Firewall
    Set-NetFirewallProfile -Profile Domain,Private,Public -Enabled False
    
    # Tắt Windows Defender Real-time Protection
    Set-MpPreference -DisableRealtimeMonitoring $true
    
    Write-Host "Đã tắt Windows Defender." -ForegroundColor Green
} catch {
    Write-Warning "Lỗi khi tắt Windows Defender: $_"
}

# --- Bước 7: Cài đặt NVIDIA Driver ---
Write-Host "Bước 7: Cài đặt NVIDIA Driver..." -ForegroundColor Cyan

# Các phần còn lại của script gốc
$Drivers = @{
    "Normal" = @{
        "Filename" = "582.53_grid_win10_win11_server2022_server_2025_dch_64bit_international.exe"
        "Hash"     = "6f1210b459efc7f29db930103533c3de9b93c2afdfa8d7b4871640c6b8638c0b"
    }
    "vGPU"   = @{
        "Filename" = "582.53_grid_win10_win11_server2022_server2025_dch_64bit_international_gcp_swl.exe"
        "Hash"     = "8e8689db080a0807cd9efae2368dc1971a60e66fd7defdb5f1c5025fdb0e0ced"
    }
}

$TempDir = [System.IO.Path]::GetTempPath()
$InstallerName = "nvidia_driver_installer.exe"
$InstallerPath = Join-Path -Path $TempDir -ChildPath $InstallerName

# --- Hằng số cho Apollo ---
$ApolloUrl = "https://github.com/ClassicOldSong/Apollo/releases/download/v0.4.6/Apollo-0.4.6.exe"
$ApolloInstallerName = "Apollo-0.4.6.exe"
$ApolloInstallerPath = Join-Path -Path $TempDir -ChildPath $ApolloInstallerName

# --- Hàm phát hiện vùng ---
function Get-GcpMultiRegion {
    # Ánh xạ tiền tố vùng sang đa vùng
    $RegionMap = @{
        "africa"       = "eu"
        "asia"         = "asia"
        "australia"    = "asia"
        "europe"       = "eu"
        "me"           = "eu"
        "northamerica" = "us"
        "southamerica" = "us"
        "us"           = "us"
    }

    Write-Host "Đang phát hiện vùng GCP..." -ForegroundColor Cyan

    try {
        # Truy vấn máy chủ metadata Google cho zone
        # Bao gồm timeout để tránh treo nếu không ở trên GCP hoặc metadata không truy cập được
        $ZoneUrl = "http://metadata.google.internal/computeMetadata/v1/instance/zone"
        $Response = Invoke-RestMethod -Uri $ZoneUrl -Headers @{"Metadata-Flavor" = "Google"} -TimeoutSec 5 -ErrorAction Stop

        # Định dạng phản hồi thường là: projects/PROJECT_ID/zones/REGION-ZONE (ví dụ: projects/123/zones/us-central1-a)
        $ZoneName = $Response.Split('/')[-1]

        # Lấy tiền tố vùng (ví dụ: 'us' từ 'us-central1-a')
        $RegionPrefix = $ZoneName.Split('-')[0]

        if ($RegionMap.ContainsKey($RegionPrefix)) {
            $MultiRegion = $RegionMap[$RegionPrefix]
            Write-Host "Đã phát hiện vùng: $RegionPrefix -> Đa vùng: $MultiRegion" -ForegroundColor Green
            return $MultiRegion
        }
    }
    catch {
        Write-Warning "Không thể phát hiện vùng GCP qua máy chủ metadata. Mặc định là 'us'."
    }

    return "us"
}

# --- Hàm phát hiện loại máy ---
function Get-MachineType {
    try {
        Write-Host "Đang phát hiện loại máy..." -ForegroundColor Cyan
        
        $MachineTypeUrl = "http://metadata.google.internal/computeMetadata/v1/instance/machine-type"
        $Response = Invoke-RestMethod -Uri $MachineTypeUrl -Headers @{"Metadata-Flavor" = "Google"} -TimeoutSec 5 -ErrorAction Stop
        
        # projects/PROJECT_ID/machineTypes/MACHINE_TYPE
        $MachineType = $Response.Split('/')[-1]
        Write-Host "Đã phát hiện loại máy: $MachineType" -ForegroundColor Green
        
        if ($MachineType -in ('g4-standard-6', 'g4-standard-12', 'g4-standard-24')) {
            return "vGPU"
        }
        
        $InstanceUrl = "http://metadata.google.internal/computeMetadata/v1/instance/"
        $Response = Invoke-RestMethod -Uri $InstanceUrl -Headers @{"Metadata-Flavor" = "Google"} -TimeoutSec 5 -ErrorAction Stop
        
        if ($Response -like "*nvidia-grid-license*") {
            # Virtual Workstation
            return "Normal" 
        }
    }
    catch {
        Write-Warning "Không thể phát hiện loại máy qua máy chủ metadata. Mặc định là 'Normal'."
    }
    return "Normal"
}

# --- Hàm phát hiện GPU ---
function Get-Mgmt-Command {
    $Command = 'Get-CimInstance'
    if (Get-Command Get-WmiObject -ErrorAction SilentlyContinue) {
        $Command = 'Get-WmiObject'
    }
    return $Command
}

function Find-GPU {
    $MgmtCommand = Get-Mgmt-Command
    try {
        # Truy vấn cụ thể cho NVIDIA (VEN_10DE) trong lớp Display hoặc 3D Controller
        $Command = "(${MgmtCommand} -query ""select DeviceID from Win32_PNPEntity Where (deviceid Like '%PCI\\VEN_10DE%') and (PNPClass = 'Display' or Name = '3D Video Controller')"" | Select-Object DeviceID -ExpandProperty DeviceID).substring(13,8)"
        $dev_id = Invoke-Expression -Command $Command
        return $dev_id
    }
    catch {
        Write-Warning "Dường như không có GPU nào được kết nối với hệ thống của bạn."
        return ""
    }
}

# --- Bước 0: Xác định URL tải xuống ---
$MultiRegion = Get-GcpMultiRegion
$MachineType = Get-MachineType

$DriverInfo = $Drivers[$MachineType]
$DriverVersionFilename = $DriverInfo["Filename"]
$ExpectedSha256 = $DriverInfo["Hash"]

$DriverUrl = "https://storage.googleapis.com/compute-gpu-installation-$MultiRegion/windows/$DriverVersionFilename"

# --- Bước 1: Kiểm tra sự hiện diện của GPU ---
Write-Host "Bước 1: Đang kiểm tra GPU NVIDIA (Kiểm tra PCI ID)..." -ForegroundColor Cyan

$skipDriverInstall = $false
$gpuId = Find-GPU

if ([string]::IsNullOrWhiteSpace($gpuId)) {
    Write-Warning "Không phát hiện GPU NVIDIA (VEN_10DE) qua kiểm tra PnP Entity. Bỏ qua cài đặt driver."
    $skipDriverInstall = $true
} else {
    Write-Host "Đã phát hiện GPU với chuỗi Device ID: $gpuId" -ForegroundColor Green
}

if (-not $skipDriverInstall) {
    # --- Bước 2: Kiểm tra nvidia-smi ---
    Write-Host "Bước 2: Đang kiểm tra cài đặt hiện có (nvidia-smi)..." -ForegroundColor Cyan

    $smiCommand = Get-Command "nvidia-smi" -ErrorAction SilentlyContinue
    $smiPathDefault = "C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"
    $smiPathSystem = "C:\Windows\System32\nvidia-smi.exe"

    if ($smiCommand -or (Test-Path $smiPathDefault) -or (Test-Path $smiPathSystem)) {
        Write-Warning "nvidia-smi đã tồn tại. Driver dường như đã được cài đặt. Bỏ qua cài đặt driver."
        $skipDriverInstall = $true
    } else {
        Write-Host "Không tìm thấy nvidia-smi. Tiến hành cài đặt." -ForegroundColor Green
    }
}

if (-not $skipDriverInstall) {
    # --- Bước 3: Tải xuống trình cài đặt ---
    Write-Host "Bước 3: Đang tải xuống driver..." -ForegroundColor Cyan
    Write-Host "Nguồn: $DriverUrl" -ForegroundColor Gray

    # Đảm bảo TLS 1.2 được bật để tải xuống
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

    try {
        # SỬA LỖI HIỆU SUẤT QUAN TRỌNG:
        # Thanh tiến trình của Invoke-WebRequest làm chậm đáng kể quá trình tải xuống trong Windows PowerShell 5.1.
        # Chúng tôi tạm thời vô hiệu hóa nó để tăng tốc quá trình truyền.
        $OriginalProgressPreference = $ProgressPreference
        $ProgressPreference = 'SilentlyContinue'

        Invoke-WebRequest -Uri $DriverUrl -OutFile $InstallerPath -UseBasicParsing

        # Khôi phục tùy chọn
        $ProgressPreference = $OriginalProgressPreference

        Write-Host "Tải xuống hoàn tất. Đã lưu tại: $InstallerPath" -ForegroundColor Green

        # --- Bước 3.1: Xác minh Checksum ---
        if (-not [string]::IsNullOrWhiteSpace($ExpectedSha256)) {
            Write-Host "Đang xác minh checksum SHA256..." -ForegroundColor Cyan
            $ComputedHash = (Get-FileHash -Path $InstallerPath -Algorithm SHA256).Hash

            if ($ComputedHash -eq $ExpectedSha256) {
                Write-Host "Checksum đã được xác minh." -ForegroundColor Green
            } else {
                # Xóa ngay tệp bị lỗi
                Remove-Item -Path $InstallerPath -Force
                Write-Warning "Checksum không khớp! Bỏ qua cài đặt driver."
                $skipDriverInstall = $true
            }
        }
    }
    catch {
        Write-Warning "Không thể tải xuống hoặc xác minh trình cài đặt. Bỏ qua cài đặt driver. Lỗi: $_"
        $skipDriverInstall = $true
    }
}

if (-not $skipDriverInstall) {
    # --- Bước 4 và 5: Thực thi và chờ ---
    Write-Host "Bước 4: Đang thực thi trình cài đặt..." -ForegroundColor Cyan
    Write-Host "Cờ sử dụng: /s /n (Âm thầm, Không khởi động lại)" -ForegroundColor Gray

    try {
        # Khởi động tiến trình với /s (âm thầm) và /n (không khởi động lại)
        $process = Start-Process -FilePath $InstallerPath -ArgumentList "/s", "/n" -PassThru -Wait -Verb RunAs

        if ($process.ExitCode -eq 0) {
            Write-Host "Cài đặt hoàn tất thành công." -ForegroundColor Green
        } else {
            Write-Warning "Cài đặt hoàn tất với mã thoát: $($process.ExitCode). Điều này có thể cho thấy cần khởi động lại hoặc cảnh báo không nghiêm trọng."
        }
    }
    catch {
        Write-Warning "Không thể thực thi trình cài đặt. Bỏ qua. Lỗi: $_"
    }

    # --- Dọn dẹp ---
    Write-Host "Đang dọn dẹp các tệp tạm thời..." -ForegroundColor Cyan
    if (Test-Path $InstallerPath) {
        Remove-Item -Path $InstallerPath -Force
    }
}

# --- Bước 8: Cấu hình và khởi động dịch vụ âm thanh ---
Write-Host ""
Write-Host "Bước 8: Đang cấu hình và khởi động dịch vụ âm thanh..." -ForegroundColor Cyan

try {
    # Cấu hình dịch vụ Audiosrv
    Write-Host "  - Cấu hình Audiosrv (Windows Audio)..." -ForegroundColor Gray
    $audiosrv = sc.exe config Audiosrv start= auto
    if ($LASTEXITCODE -eq 0) {
        Write-Host "    Đã cấu hình Audiosrv thành công." -ForegroundColor Green
    } else {
        Write-Warning "    Không thể cấu hình Audiosrv. Mã lỗi: $LASTEXITCODE"
    }

    # Khởi động dịch vụ Audiosrv
    Write-Host "  - Khởi động Audiosrv (Windows Audio)..." -ForegroundColor Gray
    $startAudiosrv = net start Audiosrv
    if ($LASTEXITCODE -eq 0) {
        Write-Host "    Đã khởi động Audiosrv thành công." -ForegroundColor Green
    } else {
        Write-Warning "    Không thể khởi động Audiosrv. Mã lỗi: $LASTEXITCODE"
    }

    # Cấu hình dịch vụ AudioEndpointBuilder
    Write-Host "  - Cấu hình AudioEndpointBuilder..." -ForegroundColor Gray
    $audioEndpoint = sc.exe config AudioEndpointBuilder start= auto
    if ($LASTEXITCODE -eq 0) {
        Write-Host "    Đã cấu hình AudioEndpointBuilder thành công." -ForegroundColor Green
    } else {
        Write-Warning "    Không thể cấu hình AudioEndpointBuilder. Mã lỗi: $LASTEXITCODE"
    }

    # Khởi động dịch vụ AudioEndpointBuilder
    Write-Host "  - Khởi động AudioEndpointBuilder..." -ForegroundColor Gray
    $startAudioEndpoint = net start AudioEndpointBuilder
    if ($LASTEXITCODE -eq 0) {
        Write-Host "    Đã khởi động AudioEndpointBuilder thành công." -ForegroundColor Green
    } else {
        Write-Warning "    Không thể khởi động AudioEndpointBuilder. Mã lỗi: $LASTEXITCODE"
    }

    Write-Host "Hoàn tất cấu hình dịch vụ âm thanh." -ForegroundColor Green
}
catch {
    Write-Warning "Đã xảy ra lỗi khi cấu hình dịch vụ âm thanh: $_"
}

# --- Bước 9: Tải và cài đặt Apollo ---
Write-Host ""
Write-Host "Bước 9: Đang tải và cài đặt Apollo..." -ForegroundColor Cyan

try {
    # Tải file Apollo về thư mục tạm
    Write-Host "  - Đang tải Apollo từ: $ApolloUrl" -ForegroundColor Gray
    
    # Tắt thanh tiến trình để tải nhanh hơn
    $OriginalProgressPreference = $ProgressPreference
    $ProgressPreference = 'SilentlyContinue'
    
    Invoke-WebRequest -Uri $ApolloUrl -OutFile $ApolloInstallerPath -UseBasicParsing
    
    # Khôi phục tùy chọn
    $ProgressPreference = $OriginalProgressPreference
    
    Write-Host "    Đã tải xuống: $ApolloInstallerPath" -ForegroundColor Green

    # Chạy file cài đặt Apollo ở chế độ âm thầm
    Write-Host "  - Đang cài đặt Apollo (chế độ âm thầm)..." -ForegroundColor Gray
    $apolloProcess = Start-Process -FilePath $ApolloInstallerPath -ArgumentList "/S" -PassThru -Wait -Verb RunAs

    if ($apolloProcess.ExitCode -eq 0) {
        Write-Host "    Cài đặt Apollo thành công." -ForegroundColor Green
    } else {
        Write-Warning "    Cài đặt Apollo hoàn tất với mã thoát: $($apolloProcess.ExitCode)."
    }

    # Xóa file cài đặt Apollo sau khi hoàn tất
    if (Test-Path $ApolloInstallerPath) {
        Remove-Item -Path $ApolloInstallerPath -Force
        Write-Host "  - Đã dọn dẹp file cài đặt Apollo." -ForegroundColor Gray
    }
}
catch {
    Write-Warning "Không thể tải hoặc cài đặt Apollo. Lỗi: $_"
}

# --- Bước 10: Tự động chạy Apollo sau khi cài đặt hoàn tất ---
Write-Host ""
Write-Host "Bước 10: Tự động chạy Apollo..." -ForegroundColor Cyan

try {
    # Kiểm tra xem Apollo đã được cài đặt chưa
    $apolloPath = "C:\Program Files\Apollo\Apollo.exe"
    if (Test-Path $apolloPath) {
        Write-Host "Đang chạy Apollo..." -ForegroundColor Gray
        Start-Process -FilePath $apolloPath -Verb RunAs
        Write-Host "Đã chạy Apollo thành công." -ForegroundColor Green
    } else {
        Write-Warning "Không tìm thấy Apollo để chạy. Có thể Apollo chưa được cài đặt hoặc đường dẫn không đúng."
    }
}
catch {
    Write-Warning "Không thể chạy Apollo. Lỗi: $_"
}

# --- Kiểm tra hệ điều hành và chạy lệnh đặc biệt cho Windows Server 2025, 2022, 2019, Windows 11, 10 ---
Write-Host ""
Write-Host "Bước 11: Kiểm tra hệ điều hành và chạy lệnh đặc biệt..." -ForegroundColor Cyan

try {
    # Lấy thông tin hệ điều hành
    $osInfo = Get-ComputerInfo | Select-Object WindowsProductName, WindowsVersion
    
    Write-Host "Thông tin hệ điều hành: $($osInfo.WindowsProductName) - $($osInfo.WindowsVersion)" -ForegroundColor Gray
    
    # Kiểm tra nếu là Windows Server 2025, 2022, 2019, Windows 11 hoặc Windows 10
    if ($osInfo.WindowsProductName -match "Server 2025|Server 2022|Server 2019|Windows 11|Windows 10") {
        Write-Host "Hệ điều hành được hỗ trợ. Đang chạy các lệnh đặc biệt..." -ForegroundColor Green
        
        # Chạy các lệnh Add-AppxPackage cho Windows Server 2025
        try {
            Write-Host "Đang chạy lệnh Add-AppxPackage cho MicrosoftWindows.Client.CBS..." -ForegroundColor Gray
            Add-AppxPackage -Register -Path "C:\Windows\SystemApps\MicrosoftWindows.Client.CBS_cw5n1h2txyewy\appxmanifest.xml" -DisableDevelopmentMode
            Write-Host "Đã chạy lệnh MicrosoftWindows.Client.CBS thành công." -ForegroundColor Green
        }
        catch {
            Write-Warning "Lỗi khi chạy lệnh MicrosoftWindows.Client.CBS: $_"
        }
        
        try {
            Write-Host "Đang chạy lệnh Add-AppxPackage cho Microsoft.UI.Xaml.CBS..." -ForegroundColor Gray
            Add-AppxPackage -Register -Path "C:\Windows\SystemApps\Microsoft.UI.Xaml.CBS_8wekyb3d8bbwe\appxmanifest.xml" -DisableDevelopmentMode
            Write-Host "Đã chạy lệnh Microsoft.UI.Xaml.CBS thành công." -ForegroundColor Green
        }
        catch {
            Write-Warning "Lỗi khi chạy lệnh Microsoft.UI.Xaml.CBS: $_"
        }
        
        try {
            Write-Host "Đang chạy lệnh Add-AppxPackage cho MicrosoftWindows.Client.Core..." -ForegroundColor Gray
            Add-AppxPackage -Register -Path "C:\Windows\SystemApps\MicrosoftWindows.Client.Core_cw5n1h2txyewy\appxmanifest.xml" -DisableDevelopmentMode
            Write-Host "Đã chạy lệnh MicrosoftWindows.Client.Core thành công." -ForegroundColor Green
        }
        catch {
            Write-Warning "Lỗi khi chạy lệnh MicrosoftWindows.Client.Core: $_"
        }
        
        Write-Host "Tất cả các lệnh đặc biệt đã được thực hiện." -ForegroundColor Green
    }
    else {
        Write-Host "Hệ điều hành không được hỗ trợ trong danh sách. Bỏ qua các lệnh đặc biệt." -ForegroundColor Yellow
    }
}
catch {
    Write-Warning "Lỗi khi kiểm tra hệ điều hành hoặc chạy lệnh đặc biệt: $_"
}

# --- Bước 12: Khởi động lại tiến trình sihost ---
Write-Host ""
Write-Host "Bước 12: Đang khởi động lại tiến trình sihost..." -ForegroundColor Cyan

try {
    Stop-Process -Name sihost -Force
    Write-Host "Đã khởi động lại sihost." -ForegroundColor Green
}
catch {
    Write-Warning "Không thể khởi động lại sihost: $_"
}

# --- Kết thúc: Khởi động AFK MODE (antiafk.py) ---
Write-Host ""
Write-Host "Bước 13: Khởi động AFK MODE (antiafk.py)..." -ForegroundColor Cyan

try {
    if (Test-Path "C:\antiafk.py") {
        Write-Host "Đang khởi động antiafk.py..." -ForegroundColor Gray
        if (Get-Command python -ErrorAction SilentlyContinue) {
            Start-Process -FilePath "python" -ArgumentList "C:\antiafk.py"
            Write-Host "Đã khởi động antiafk.py thành công." -ForegroundColor Green
        } elseif (Get-Command py -ErrorAction SilentlyContinue) {
            Start-Process -FilePath "py" -ArgumentList "-3", "C:\antiafk.py"
            Write-Host "Đã khởi động antiafk.py thành công." -ForegroundColor Green
        } else {
            Write-Warning "Không tìm thấy Python. Hãy cài Python rồi chạy: python C:\antiafk.py"
        }
    } else {
        Write-Warning "Không tìm thấy C:\antiafk.py. Không thể khởi động AFK MODE."
    }
}
catch {
    Write-Warning "Không thể khởi động antiafk.py: $_"
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "        CÀI ĐẶT HOÀN TẤT" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "✓ Driver NVIDIA đã được cài đặt" -ForegroundColor White
Write-Host "✓ Dịch vụ âm thanh đã được cấu hình và khởi động" -ForegroundColor White
Write-Host "✓ Apollo đã được cài đặt" -ForegroundColor White
Write-Host "✓ WinRAR đã được cài đặt" -ForegroundColor White
Write-Host "✓ DirectX Jun2010 đã được cài đặt" -ForegroundColor White
Write-Host "✓ Visual C++ Redistributable đã được cài đặt" -ForegroundColor White
Write-Host "✓ Wallpaper đã được đặt" -ForegroundColor White
Write-Host "✓ Tất cả cổng Windows đã bị tắt" -ForegroundColor White
Write-Host "✓ Windows Defender đã bị tắt" -ForegroundColor White
Write-Host "✓ AFK MODE đã được khởi động" -ForegroundColor White
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
