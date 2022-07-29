#!/bin/bash

systemctl stop vsmp.service || :
cp vsmp.service /etc/systemd/system/
echo "Service file copied to /etc/systemd/system/vsmp.service"
systemctl reenable vsmp.service
systemctl start vsmp.service
