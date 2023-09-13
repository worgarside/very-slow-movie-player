#!/bin/bash

systemctl stop vsmp.service || :
cp vsmp.service /etc/systemd/system/
echo "Service file copied to /etc/systemd/system/vsmp.service"
systemctl disable vsmp.service
systemctl enable vsmp.service
systemctl start vsmp.service
