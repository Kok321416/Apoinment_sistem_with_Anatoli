"""Free TCP port by terminating listener PIDs. Usage: python scripts/free_port.py 8000"""
import os
import re
import signal
import subprocess
import sys
import time


def pids_on_port(port: int) -> set[int]:
    found: set[int] = set()
    try:
        out = subprocess.check_output(
            ["ss", "-lptn", f"sport = :{port}"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        found.update(int(x) for x in re.findall(r"pid=(\d+)", out))
    except Exception:
        pass
    return found


def port_is_bindable(port: int) -> tuple[bool, str | None]:
    import errno
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", port))
        return True, None
    except OSError as exc:
        hint = errno.errorcode.get(exc.errno, str(exc.errno))
        return False, f"{exc} ({hint})"
    finally:
        sock.close()


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1].isdigit():
        print("Usage: python scripts/free_port.py <port>", file=sys.stderr)
        return 2
    port = int(sys.argv[1])

    for attempt in range(3):
        pids = pids_on_port(port)
        if not pids:
            ok, err = port_is_bindable(port)
            if ok:
                print(f"Port {port} is free")
                return 0
            print(f"Port {port} looks free in ss but is not bindable (attempt {attempt + 1}): {err}")
            time.sleep(2)
            continue
        print(f"Port {port} busy, killing PIDs: {sorted(pids)} (attempt {attempt + 1})")
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        time.sleep(2)

    for pid in pids_on_port(port):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    time.sleep(1)

    remaining = pids_on_port(port)
    if remaining:
        print(f"ERROR: port {port} still in use by PIDs: {sorted(remaining)}", file=sys.stderr)
        return 1
    ok, err = port_is_bindable(port)
    if not ok:
        print(f"ERROR: port {port} is not bindable on 127.0.0.1: {err}", file=sys.stderr)
        return 1
    print(f"Port {port} is free")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
