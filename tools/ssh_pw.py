#!/usr/bin/env python3
"""ssh_pw.py – einen Befehl per SSH mit Passwort ausführen (ohne sshpass).

Aufruf: SSHPASS=147147 python3 tools/ssh_pw.py user@172.16.42.1 'befehl'
"""
import os
import pty
import select
import sys

host, cmd = sys.argv[1], sys.argv[2]
pw = os.environ.get("SSHPASS", "147147").encode() + b"\n"
argv = ["ssh", "-o", "StrictHostKeyChecking=accept-new",
        "-o", "PreferredAuthentications=password,keyboard-interactive",
        "-o", "PubkeyAuthentication=no", host, cmd]
pid, fd = pty.fork()
if pid == 0:
    os.execvp("ssh", argv)
sent = 0
buf = b""
while True:
    try:
        r, _, _ = select.select([fd], [], [], 120)
        if not r:
            break
        data = os.read(fd, 65536)
    except OSError:
        break
    if not data:
        break
    buf += data
    if sent < 3 and b"assword" in buf[-200:]:
        os.write(fd, pw)
        sent += 1
        buf = b""
        continue
    sys.stdout.buffer.write(data)
    sys.stdout.flush()
_, st = os.waitpid(pid, 0)
sys.exit(os.waitstatus_to_exitcode(st))
