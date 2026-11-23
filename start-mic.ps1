<#
.SYNOPSIS
    One-click launcher: use an Android phone as a Windows microphone over Wi-Fi.

.DESCRIPTION
    1. Checks that Python, adb and the Python packages are available.
    2. If the phone is plugged in by USB, switches adb to the fixed TCP port
       5555 and remembers the phone's Wi-Fi IP address. This is only needed
       once after each phone reboot; the cable can then be unplugged.
    3. Streams the microphone over Wi-Fi with automatic reconnection, until
       the window is closed or Ctrl+C is pressed.

    To launch it with a double-click, use a shortcut whose target is:
        powershell.exe -NoProfile -ExecutionPolicy Bypass -File "<path>\start-mic.ps1"

.EXAMPLE
    .\start-mic.ps1
    .\start-mic.ps1 -PhoneIp 192.168.1.172 -Gain 2.0 -Latency 60
#>
param(
    [string]$PhoneIp,
    [string]$Gain = '1.0',
    [string]$Latency = 'low'
)

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$ipFile = Join-Path $here '.phone-ip'
$tcpPort = 5555
$Host.UI.RawUI.WindowTitle = 'Phone microphone'

function Stop-WithError([string]$message) {
    Write-Host "Error: $message" -ForegroundColor Red
    Read-Host 'Press Enter to close'
    exit 1
}

# Reload PATH so tools installed after this session started (winget) are found.
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
            [Environment]::GetEnvironmentVariable('Path', 'User')

# --- Prerequisites -----------------------------------------------------------
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Stop-WithError 'python not found. Install Python 3 from python.org (tick "Add to PATH").'
}
if (-not (Get-Command adb -ErrorAction SilentlyContinue)) {
    Stop-WithError 'adb not found. Install it with: winget install --id Google.PlatformTools'
}
python -c 'import sounddevice, numpy' 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host '[+] Installing Python packages (sounddevice, numpy)'
    python -m pip install --quiet sounddevice numpy
    if ($LASTEXITCODE -ne 0) { Stop-WithError 'could not install sounddevice and numpy.' }
}

# --- Phone plugged in by USB? Switch it to the fixed Wi-Fi port. -------------
$usbSerial = $null
foreach ($line in @(adb devices | Select-Object -Skip 1)) {
    $parts = $line -split '\s+'
    # USB serials contain neither ':' (IP:port) nor '_adb-tls' (wireless debugging).
    if ($parts.Count -ge 2 -and $parts[1] -eq 'device' -and $parts[0] -notmatch ':|_adb-tls') {
        $usbSerial = $parts[0]
        break
    }
}

if ($usbSerial) {
    Write-Host "[+] Phone found on USB ($usbSerial)"
    $inet = adb -s $usbSerial shell ip -f inet addr show wlan0 |
            Select-String 'inet (\d+\.\d+\.\d+\.\d+)'
    if ($inet) {
        $detectedIp = $inet.Matches[0].Groups[1].Value
        Set-Content -Path $ipFile -Value $detectedIp -Encoding ascii
        Write-Host "[+] Phone Wi-Fi address: $detectedIp (saved)"
    } else {
        Write-Host '[!] Could not read the phone Wi-Fi address. Is Wi-Fi on?' -ForegroundColor Yellow
    }
    Write-Host "[+] Switching adb to Wi-Fi port $tcpPort"
    adb -s $usbSerial tcpip $tcpPort | Out-Host
    Start-Sleep -Seconds 3
    Write-Host '[+] You can unplug the USB cable now.' -ForegroundColor Green
}

# --- Which address to connect to ---------------------------------------------
if ($PhoneIp) {
    Set-Content -Path $ipFile -Value $PhoneIp -Encoding ascii  # remember it
} elseif (Test-Path $ipFile) {
    $PhoneIp = (Get-Content -Path $ipFile -TotalCount 1).Trim()
}
if (-not $PhoneIp) {
    Stop-WithError ('phone address unknown. Plug the phone in by USB once ' +
                    '(USB debugging on) and run this again, or pass -PhoneIp.')
}

# --- Stream (reconnects automatically) ---------------------------------------
Write-Host "[+] Phone: ${PhoneIp}:$tcpPort  -  close this window or press Ctrl+C to stop"
python (Join-Path $here 'audiosource.py') run --connect "${PhoneIp}:$tcpPort" --gain $Gain --latency $Latency
if ($LASTEXITCODE -ne 0) {
    Write-Host ''
    Write-Host 'If the phone rebooted, plug it in by USB once and run this again.' -ForegroundColor Yellow
    Read-Host 'Press Enter to close'
}
