# Audio Source for Windows and Linux

> Fork of [gdzx/audiosource](https://github.com/gdzx/audiosource) that adds a
> **Windows client**: USB or Wi-Fi, low latency, automatic reconnection and a
> one-click launcher. The Android app and the Linux client are unchanged.

Audio Source forwards Android microphone audio through ADB, so you can use your
Android device as a USB or Wi-Fi microphone: on Linux through PulseAudio or
PipeWire, and on Windows through a virtual audio cable (VB-CABLE). It works
with any application: video calls (Google Meet, Teams, Zoom, Discord), voice
dictation, OBS...

![screenshot](assets/screenshot.png)

## Requirements

- Device with at least Android 4.0 (API level 14), but fully tested only on
  Android 10 (API level 29) so your mileage may vary.
- Windows 10/11 machine: see [Windows](#windows).
- GNU/Linux machine with:
  - Android SDK Platform Tools (requires `adb` in `PATH`).
  - PulseAudio or PipeWire with PulseAudio support (requires `pactl` in
    `PATH`).
  - Python 3 (requires `python3` in `PATH`).

## Windows

The `audiosource.py` client plays the phone's microphone audio into a virtual
audio cable, which Windows applications then use as a microphone.

### Setup (once)

1. Install the tools:
   - Android SDK Platform Tools: `winget install --id Google.PlatformTools`
   - [VB-CABLE](https://vb-audio.com/Cable/) (free virtual audio cable), then
     reboot.
   - [Python 3](https://www.python.org/downloads/) (tick "Add to PATH"). The
     launcher installs the `sounddevice` and `numpy` packages by itself.
2. Install the Audio Source app on the phone and enable USB debugging (see
   [Installation](#installation)).
3. In `mmsys.cpl`, set both **CABLE Input** (Playback) and **CABLE Output**
   (Recording) to *2 channels, 16 bit, 48000 Hz*, and make **CABLE Output** the
   default and default communication device.

### One-click launch (Wi-Fi)

`start-mic.ps1` does everything: it checks the prerequisites, switches the
phone to Wi-Fi when it is plugged in by USB, remembers its address, then streams
the microphone with automatic reconnection.

1. Plug the phone in by USB, right-click `start-mic.ps1` and choose
   **Run with PowerShell**.
2. When it says so, unplug the cable. The microphone keeps working over Wi-Fi
   until you close the window.

Next times, just run it again: no cable needed, until the phone reboots (then
plug it in by USB once more). For a desktop shortcut, use this target:

```text
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\path\to\start-mic.ps1"
```

Options: `-PhoneIp 192.168.1.50` (address to use, remembered), `-Gain 2.0`,
`-Latency 60`.

### Command line

```powershell
python audiosource.py devices                    # list audio outputs
python audiosource.py run                        # USB
python audiosource.py run --connect PHONE_IP     # Wi-Fi (after adb tcpip 5555)
```

Options for `run`:

- `--connect IP[:PORT]`: Wi-Fi mode, reconnects after drops (default port:
  `5555`).
- `--device NAME`: output device name substring (default: `CABLE Input`).
- `--gain 2.0`: volume multiplier if the sound is too low.
- `--latency low|high|MS`: output buffer (default: `low`). Raise it, for
  example `--latency 60`, if the sound crackles over Wi-Fi.
- `--hostapi WASAPI|DirectSound|MME`: force a Windows audio API. By default the
  lowest-latency one (WASAPI) is tried first, then the others.
- `--once`: stop when the connection drops. By default the client reconnects
  automatically until you press Ctrl+C.
- `--port N`: local TCP port used by `adb forward` (default: `34567`).

Use `-s SERIAL` before the command to select a device when several are connected.

### Wi-Fi notes

Android's _Wireless debugging_ changes port and may turn itself off when the
phone sleeps (notably on Xiaomi/HyperOS). That is why this client uses a fixed
port instead: `adb tcpip 5555` over USB, then `--connect PHONE_IP`. The fixed
port lasts until the phone reboots.

For a stable connection: reserve the phone's IP address in your router (static
DHCP lease), prefer 5 GHz Wi-Fi, keep the phone charging, and disable battery
restrictions for the Audio Source app.

## Installation

[<img src="assets/badge_fdroid.png"
     alt="Get it on F-Droid"
     height="80">](https://f-droid.org/packages/fr.dzx.audiosource/)
[<img src="assets/badge_github.png"
    alt="Get it on GitHub"
    height="80">](https://github.com/gdzx/audiosource/releases/latest)

On your Android device:

1. Go to _Settings > About phone_ then tap _Build number_ 7 times to enable the
   _Developer options_ menu.
2. In _Settings > System > Developer options_ enable _USB debugging_ (Android
   Debug Bridge).
3. Install the Audio Source Android app:
   - (Recommended) Get it on [F-Droid](https://f-droid.org/packages/fr.dzx.audiosource/).
   - Or download the APK from the [latest release](https://github.com/gdzx/audiosource/releases/latest).
   - Or build it from source (see [Build and install](#build-and-install)).

On your Linux PC:

1. Download the `audiosource` client script from the [latest
   release](https://github.com/gdzx/audiosource/releases/latest) (look for a
   file named `audiosource` in the assets section).
2. Open a terminal in the downloads directory (or `cd` into it).
3. Then make the script executable with `chmod a+x ./audiosource`.

## Usage

1. Connect your Android device to your PC via a USB cable. (Note that wireless
   debugging should also work, at the cost of increased latency and jitter.)
2. On your phone, allow USB debugging, if requested.
3. In the terminal, run `./audiosource run`. This starts Audio Source and
   immediately attempts to forward the microphone audio.
4. On your phone, grant microphone/recording permissions, if requested.
5. If the volume is too low, adjust it with `./audiosource volume 200%`
   (replace `200%` with the desired level). You will likely need a volume
   level higher than 100%.

## Troubleshooting

If you encounter the `adb not found` error, it means that the `adb` command is
either not installed or not in your system's `PATH`. On most distributions you
can install it via the package manager:

```console
# Arch Linux
$ pacman -S android-tools

# Debian/Ubuntu
$ apt install android-tools-adb
```

After installation, verify that it is working with `adb --version`, and re-run
`audiosource`.

Common tips:

- Ensure your phone is connected, USB debugging is enabled, and the PC is
  authorized (check your phone for a prompt to allow the connection).
- Run `adb devices` to confirm your phone is detected (it should show a serial
  number and "device").
- If no devices are found, try a different USB cable/port or try to re-enable
  USB debugging.

## Multi-device

If you have multiple devices connected then you will have to specify the serial
number of the device you would like to forward audio to. Device serial numbers
can be found by running `adb devices`. 

Then you can specify the serial number as an argument:

```console
$ ./audiosource -s 1234 run
```

Or by setting the `ANDROID_SERIAL` environment variable:

```console
$ ANDROID_SERIAL=1324 ./audiosource run
```

You can utilize job control to forward audio from multiple devices
simultaneously as follows:

```console
$ ./audiosource -s shiba run &  # press ENTER to regain control of your terminal
$ ./audiosource -s 192.168.1.188:39857 run
```

## Build and install

Run `./gradlew tasks` to list the available commands.

### Debug

```console
$ ./audiosource build
$ ./audiosource install
```

### Release

1. Generate a Java KeyStore:

   ```console
   $ keytool -keystore /home/user/android.jks -genkey -alias release \
          -keyalg RSA -keysize 2048 -validity 30000
   ```

2. Create `keystore.properties` in the project root directory containing:

   ```ini
   storeFile=/home/user/android.jks
   storePassword=STORE_PASS
   keyAlias=release
   keyPassword=KEY_PASS
   ```

3. Build and install:

   ```console
   $ export AUDIOSOURCE_PROFILE=release
   $ ./audiosource build
   $ ./audiosource install
   ```

## Acknowledgement

[sndcpy](https://github.com/rom1v/sndcpy) for the initial implementation of
audio playback forwarding.

## License

This project is licensed under the MIT license ([LICENSE](LICENSE) or
http://opensource.org/licenses/MIT).
