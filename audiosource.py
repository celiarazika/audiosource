#!/usr/bin/env python3
"""Audio Source client for Windows.

Forwards the microphone audio captured by the Audio Source Android app
(through ADB) to a virtual audio cable, so Windows applications can use the
phone as a microphone.

Windows does not have PulseAudio, so the audio is played into an output device
(by default "CABLE Input" from VB-Audio Virtual Cable). Windows applications
then record from the matching input device "CABLE Output".

Requirements:
  - Python 3 (on PATH, or use the `py` launcher)
  - Android SDK Platform Tools (adb on PATH)
  - VB-CABLE (https://vb-audio.com/Cable/), or any virtual audio cable
  - pip install sounddevice numpy
"""

import argparse
import os
import shutil
import socket
import subprocess
import sys

PKG = "fr.dzx.audiosource"
ACTIVITY = f"{PKG}/.MainActivity"
SOCKET_NAME = "audiosource"  # abstract socket opened by the Android app
RATE = 44100
CHANNELS = 1
SAMPLE_BYTES = 2  # s16
CHUNK = 1024 * SAMPLE_BYTES
DEFAULT_PORT = 34567
DEFAULT_DEVICE = "CABLE Input"
PERMISSIONS = [
    "android.permission.POST_NOTIFICATIONS",
    "android.permission.RECORD_AUDIO",
]


def die(msg, code=1):
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(code)


def adb_cmd(serial, *args):
    cmd = ["adb"]
    if serial:
        cmd += ["-s", serial]
    return cmd + list(args)


def run_adb(serial, *args, capture=False):
    return subprocess.run(
        adb_cmd(serial, *args),
        check=False,
        capture_output=capture,
        text=capture,
    )


def check_adb():
    if shutil.which("adb") is None:
        die("adb not found. Install Android SDK Platform Tools and add it to PATH.")


def check_permissions(serial):
    """Grant the required permissions. Return True if all are granted."""
    dumpsys = run_adb(serial, "exec-out", "dumpsys", "package", PKG, capture=True)
    if dumpsys.returncode != 0:
        die("could not query the Audio Source package. Is the app installed?")

    ok = True
    for perm in PERMISSIONS:
        granted = f"{perm}: granted=true" in dumpsys.stdout
        if not granted:
            granted = run_adb(serial, "exec-out", "pm", "grant", PKG, perm).returncode == 0
        print(f"{perm}: granted={'true' if granted else 'false'}")
        ok = ok and granted
    return ok


HOSTAPI_PREFERENCE = ["WASAPI", "DirectSound", "MME"]  # lowest latency first


def hostapi_name(sd, dev):
    return sd.query_hostapis(dev["hostapi"])["name"]


def find_output_devices(sd, name, hostapi=None):
    """Return matching output device indexes, lowest-latency host API first."""
    matches = []
    for index, dev in enumerate(sd.query_devices()):
        if dev["max_output_channels"] == 0 or name.lower() not in dev["name"].lower():
            continue
        api = hostapi_name(sd, dev)
        if hostapi and hostapi.lower() not in api.lower():
            continue
        rank = next(
            (i for i, p in enumerate(HOSTAPI_PREFERENCE) if p.lower() in api.lower()),
            len(HOSTAPI_PREFERENCE),
        )
        matches.append((rank, index))
    return [index for _, index in sorted(matches)]


def parse_latency(value):
    if value in ("low", "high"):
        return value
    try:
        return float(value) / 1000  # milliseconds -> seconds
    except ValueError:
        raise argparse.ArgumentTypeError("latency must be 'low', 'high' or milliseconds")


def open_stream(sd, device_index, latency):
    """Open the output stream, letting WASAPI resample if the rate differs."""
    kwargs = dict(
        samplerate=RATE,
        channels=CHANNELS,
        dtype="int16",
        device=device_index,
        latency=latency,
    )
    api = hostapi_name(sd, sd.query_devices(device_index))
    if "wasapi" in api.lower():
        try:
            kwargs["extra_settings"] = sd.WasapiSettings(auto_convert=True)
        except TypeError:
            pass  # older sounddevice without auto_convert
    return sd.RawOutputStream(**kwargs)


def apply_gain(samples, gain):
    import numpy as np

    scaled = samples.astype(np.float32) * gain
    return np.clip(scaled, -32768, 32767).astype(np.int16)


def pump(sock, stream, gain):
    """Read PCM from the socket and write it to the output stream until EOF."""
    import numpy as np

    while True:
        data = sock.recv(CHUNK)
        if not data:
            break
        # Keep whole 16-bit samples only.
        usable = len(data) - (len(data) % SAMPLE_BYTES)
        if usable == 0:
            continue
        samples = np.frombuffer(data[:usable], dtype=np.int16)
        if gain != 1.0:
            samples = apply_gain(samples, gain)
        stream.write(samples)


def cmd_run(args):
    import sounddevice as sd

    check_adb()

    candidates = find_output_devices(sd, args.device, args.hostapi)
    if not candidates:
        die(
            f"no output device matching '{args.device}'. "
            "Install VB-CABLE, or pick another device with --device."
        )

    # Open the audio output first: fall back to slower host APIs if needed.
    stream = None
    for device_index in candidates:
        try:
            stream = open_stream(sd, device_index, args.latency)
            break
        except sd.PortAudioError as e:
            dev = sd.query_devices(device_index)
            print(f"[!] {hostapi_name(sd, dev)} '{dev['name']}' unavailable: {e}")
    if stream is None:
        die("could not open any matching output device.")

    dev = sd.query_devices(device_index)
    print(
        f"[+] Output: [{device_index}] {dev['name']} ({hostapi_name(sd, dev)}), "
        f"latency {stream.latency * 1000:.0f} ms"
    )

    if args.serial:
        listed = run_adb("", "devices", capture=True).stdout.splitlines()[1:]
        serials = [line.split()[0] for line in listed if line.strip()]
        if args.serial not in serials:
            print(f"[!] '{args.serial}' is not in 'adb devices'. Connected devices:")
            for s in serials or ["(none)"]:
                print(f"      {s}")
            print("    Use one of these names with -s, or omit -s if only one is connected.")
            print("    (The port shown by 'adb pair' is only for pairing, not for -s.)")

    print("[+] Waiting for device", args.serial or "")
    run_adb(args.serial, "wait-for-device")

    print("[+] Checking permissions")
    if not check_permissions(args.serial):
        die(
            "could not grant permissions. Grant them manually on the phone "
            "(Settings > Apps > Audio Source > Permissions)."
        )

    print("[+] Starting Audio Source")
    run_adb(args.serial, "shell", "am", "start", ACTIVITY)

    print(f"[+] Forwarding audio to '{args.device}' (port {args.port})")
    fwd = run_adb(
        args.serial, "forward", f"tcp:{args.port}", f"localabstract:{SOCKET_NAME}"
    )
    if fwd.returncode != 0:
        die("adb forward failed.")

    try:
        with socket.create_connection(("127.0.0.1", args.port), timeout=10) as sock:
            sock.settimeout(None)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            with stream:
                print("[+] Streaming. Press Ctrl+C to stop.")
                pump(sock, stream, args.gain)
    except KeyboardInterrupt:
        print("\n[+] Stopped")
    except OSError as e:
        die(f"connection to the phone failed: {e}")
    finally:
        run_adb(args.serial, "forward", "--remove", f"tcp:{args.port}")
    return 0


def cmd_devices(args):
    import sounddevice as sd

    print("Output devices (use one with --device / --hostapi):")
    for index, dev in enumerate(sd.query_devices()):
        if dev["max_output_channels"] > 0:
            print(f"  [{index}] {dev['name']}  ({hostapi_name(sd, dev)})")
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        description="Use an Android phone as a microphone on Windows (via ADB)."
    )
    p.add_argument("-s", "--serial", default=os.environ.get("ANDROID_SERIAL", ""),
                   help="device serial (default: $ANDROID_SERIAL or the only device)")
    sub = p.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="start forwarding the microphone audio")
    run.add_argument("--device", default=DEFAULT_DEVICE,
                     help=f"output device name substring (default: '{DEFAULT_DEVICE}')")
    run.add_argument("--port", type=int, default=DEFAULT_PORT,
                     help=f"local TCP port used by adb forward (default: {DEFAULT_PORT})")
    run.add_argument("--gain", type=float, default=1.0,
                     help="volume multiplier, e.g. 2.0 for +6 dB (default: 1.0)")
    run.add_argument("--latency", type=parse_latency, default="low",
                     help="output latency: 'low', 'high' or milliseconds, e.g. 40 "
                          "(raise it if the sound crackles; default: low)")
    run.add_argument("--hostapi", default=None,
                     help="force a Windows audio API: WASAPI, DirectSound or MME "
                          "(default: try WASAPI first)")
    run.set_defaults(func=cmd_run)

    devices = sub.add_parser("devices", help="list audio output devices")
    devices.set_defaults(func=cmd_devices)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command in ("run", "devices"):
        try:
            import sounddevice  # noqa: F401
            import numpy  # noqa: F401
        except ImportError:
            die("missing Python packages. Run: pip install sounddevice numpy")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
