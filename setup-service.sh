#!/bin/bash
set -x

cp laundryalarm.service /lib/systemd/system/laundryalarm.service
chmod 644 /lib/systemd/system/laundryalarm.service
systemctl daemon-reload
systemctl enable laundryalarm.service
systemctl start laundryalarm.service
systemctl status laundryalarm.service
