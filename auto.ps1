<#
.SYNOPSIS
    Trình cài đặt NVIDIA Driver tự động cho Windows Server 2019+

.DESCRIPTION
    1. Xác định đa vùng GCP dựa trên metadata của instance.
    2. Kiểm tra sự hiện diện của GPU NVIDIA sử dụng PCI Vendor ID (10DE).
    3. Kiểm tra xem nvidia-smi đã được cài đặt chưa.
    4. Tải xuống trình cài đặt driver theo vùng cụ thể.
    5. Cài đặt driver một cách âm thầm.
    6. Dọn dẹp các tệp cài đặt.
    7. Cấu hình và khởi động dịch vụ âm thanh (Audiosrv và AudioEndpointBuilder).
    8. Tải và cài đặt Apollo ở chế độ âm thầm.

.NOTES
    Chạy script này với quyền Quản trị viên.
#>

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

# --- Hằng số & Cấu hình ---
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

$gpuId = Find-GPU

if ([string]::IsNullOrWhiteSpace($gpuId)) {
    Write-Warning "Không phát hiện GPU NVIDIA (VEN_10DE) qua kiểm tra PnP Entity. Đang thoát."
    Exit
} else {
    Write-Host "Đã phát hiện GPU với chuỗi Device ID: $gpuId" -ForegroundColor Green
}

# --- Bước 2: Kiểm tra nvidia-smi ---
Write-Host "Bước 2: Đang kiểm tra cài đặt hiện có (nvidia-smi)..." -ForegroundColor Cyan

$smiCommand = Get-Command "nvidia-smi" -ErrorAction SilentlyContinue
$smiPathDefault = "C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"
$smiPathSystem = "C:\Windows\System32\nvidia-smi.exe"

if ($smiCommand -or (Test-Path $smiPathDefault) -or (Test-Path $smiPathSystem)) {
    Write-Warning "nvidia-smi đã tồn tại. Driver dường như đã được cài đặt. Đang thoát."
    Exit
} else {
    Write-Host "Không tìm thấy nvidia-smi. Tiến hành cài đặt." -ForegroundColor Green
}

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
            Write-Error "Checksum không khớp! Dự kiến: $ExpectedSha256, Tính toán: $ComputedHash"
            Exit
        }
    }
}
catch {
    Write-Error "Không thể tải xuống hoặc xác minh trình cài đặt. Lỗi: $_"
    Exit
}

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
    Write-Error "Không thể thực thi trình cài đặt. Lỗi: $_"
    Exit
}

# --- Dọn dẹp ---
Write-Host "Đang dọn dẹp các tệp tạm thời..." -ForegroundColor Cyan
if (Test-Path $InstallerPath) {
    Remove-Item -Path $InstallerPath -Force
}

# --- Bước 6: Cấu hình và khởi động dịch vụ âm thanh ---
Write-Host ""
Write-Host "Bước 6: Đang cấu hình và khởi động dịch vụ âm thanh..." -ForegroundColor Cyan

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

# --- Bước 7: Tải và cài đặt Apollo ---
Write-Host ""
Write-Host "Bước 7: Đang tải và cài đặt Apollo..." -ForegroundColor Cyan

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

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "        CÀI ĐẶT HOÀN TẤT" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "✓ Driver NVIDIA đã được cài đặt" -ForegroundColor White
Write-Host "✓ Dịch vụ âm thanh đã được cấu hình và khởi động" -ForegroundColor White
Write-Host "✓ Apollo đã được cài đặt" -ForegroundColor White
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
