#!/bin/bash
set -euo pipefail
exec > >(tee /var/log/userdata.log) 2>&1

echo ">>> Starting userdata provisioning — $(date)"

# ── System update ──
apt-get update -y
apt-get upgrade -y

# ── Docker CE (official repo) ──
apt-get install -y ca-certificates curl gnupg lsb-release

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
  > /etc/apt/sources.list.d/docker.list

apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin

systemctl enable docker
systemctl start docker

# ── Java 21 ──
apt-get install -y openjdk-21-jdk

# ── Jenkins (official repo) ──
curl -fsSL https://pkg.jenkins.io/debian-stable/jenkins.io-2026.key \
  | tee /usr/share/keyrings/jenkins-keyring.asc > /dev/null

echo \
  "deb [signed-by=/usr/share/keyrings/jenkins-keyring.asc] \
  https://pkg.jenkins.io/debian-stable binary/" \
  > /etc/apt/sources.list.d/jenkins.list

apt-get update -y
apt-get install -y jenkins

systemctl enable jenkins
systemctl start jenkins

# ── Add users to docker group ──
usermod -aG docker ubuntu
usermod -aG docker jenkins

# Restart Jenkins so it picks up the docker group membership
systemctl restart jenkins

echo ">>> Userdata provisioning complete — $(date)"
