#!/bin/bash

PASS="openwifi"
DEVICE_IP="192.168.10.122"

echo "DEPLOYING ow-decoder TO $DEVICE_IP:"

echo " > 1. Removing keys before SSH-ing"
ssh-keygen -f "~/.ssh/known_hosts" -R $DEVICE_IP

echo " > 2. Compiling..."
cross build --release --target armv7-unknown-linux-gnueabihf

echo " > 3. Killing current httpd process (if possible), removing the main app, the /opt/ow-decoder dir, and re-creating /opt/ow-decoder dir"
sshpass -p "$PASS" ssh -T -o StrictHostKeyChecking=no root@$DEVICE_IP <<'REMOTE'
set -e
rm -rf /opt/ow-decoder
mkdir -p /opt/ow-decoder
REMOTE

echo " > 4. Transfering the new executable into /opt/ow-decoder directory"
sshpass -p "$PASS" scp -o StrictHostKeyChecking=no target/armv7-unknown-linux-gnueabihf/release/ow-decoder root@$DEVICE_IP:/opt/ow-decoder/ow-decoder.new

echo " > 5. Re-mounting the drive, transfering ow-decoder into the root dir"
sshpass -p "$PASS" ssh -T -o StrictHostKeyChecking=no root@$DEVICE_IP <<'REMOTE'
set -e
killall -q ow-decoder || :
mount -o remount,rw / || true
install -m 755 /opt/ow-decoder/ow-decoder.new /root/ow-decoder
REMOTE

echo " DONE."