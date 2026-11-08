#!/usr/bin/env bash
# Connect to the running SSH ramdisk (usbmuxd without pairing, as SSHRD requires on Linux)
cd "$(dirname "$0")/../src/SSHRD_Script"
PORT="${PORT:-2224}"
sudo -n true 2>/dev/null || { echo "sudo needs a password – please run in the terminal: sudo -v"; exit 1; }
sudo systemctl stop usbmuxd.socket usbmuxd.service 2>/dev/null
sudo pkill -x usbmuxd 2>/dev/null; sleep 1
sudo sh -c 'nohup usbmuxd -p -f -v > /tmp/usbmuxd.log 2>&1 &'
sleep 4
nohup Linux/iproxy $PORT 22 > /tmp/iproxy.log 2>&1 &
sleep 2
Linux/sshpass -p alpine ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 -p$PORT root@localhost 'uname -a; ls /dev/disk0*' 2>&1
echo "--- usbmuxd.log"; tail -8 /tmp/usbmuxd.log 2>/dev/null
