#!/bin/bash
set -x

mkdir -p /var/log/laundryalarm
chown pi.pi /var/log/laundryalarm
touch /var/log/laundryalarm/laundryalarm.log
chown pi.pi /var/log/laundryalarm/laundryalarm.log
cp laundryalarm.service /lib/systemd/system/laundryalarm.service
chmod 644 /lib/systemd/system/laundryalarm.service
systemctl daemon-reload
systemctl enable laundryalarm.service
systemctl start laundryalarm.service
systemctl status laundryalarm.service
