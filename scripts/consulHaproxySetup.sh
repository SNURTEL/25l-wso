#!/usr/bin/env bash

set -euo pipefail

if [ "$EUID" -ne 0 ]; then
  echo "Please run the script as root (sudo)."
  exit 1
fi

which apt || { echo "This script is intended for Debian-based systems."; exit 1; }

CONSUL_VERSION="1.16.2"
CONSUL_TEMPLATE_VERSION="0.31.0"
CONSUL_CONFIG_DIR="/etc/consul.d"
CONSUL_DATA_DIR="/opt/consul"
HAPROXY_CONFIG_DIR="/etc/haproxy"
HAPROXY_TEMPLATE_FILE="$HAPROXY_CONFIG_DIR/haproxy.ctmpl"
HAPROXY_OUTPUT_CONFIG_FILE="$HAPROXY_CONFIG_DIR/haproxy.cfg"
HAPROXY_ERROR_PAGES_DIR="/etc/proxy-errors"

CONSUL_INSTALL_DIR="/usr/share/consul"
CONSUL_TEMPLATE_INSTALL_DIR="/usr/share/consul-template"
SYMLINK_DIR="/usr/local/bin"

mkdir -p "$CONSUL_INSTALL_DIR"
mkdir -p "$CONSUL_TEMPLATE_INSTALL_DIR"

LOCAL_IP="127.0.0.1" #TODO

export DEBIAN_FRONTEND=noninteractive

echo "--- Starting Consul and Consul-Template Configuration ---"
echo "1. Updating package list and installing unzip, curl, git..."
apt update -y
apt install -y unzip curl git

echo "2. Installing Consul (development server)..."
curl -fsSL https://releases.hashicorp.com/consul/${CONSUL_VERSION}/consul_${CONSUL_VERSION}_linux_amd64.zip -o /tmp/consul.zip
unzip /tmp/consul.zip -d "${CONSUL_INSTALL_DIR}/"
chmod u+x "${CONSUL_INSTALL_DIR}/consul"
ln -s "${CONSUL_INSTALL_DIR}/consul" "${SYMLINK_DIR}/consul"
chmod u+x "${SYMLINK_DIR}/consul"
rm /tmp/consul.zip
echo "Consul version: $(consul --version)"

echo "3. Installing Consul-Template..."
curl -fsSL https://releases.hashicorp.com/consul-template/${CONSUL_TEMPLATE_VERSION}/consul-template_${CONSUL_TEMPLATE_VERSION}_linux_amd64.zip -o /tmp/consul-template.zip
unzip /tmp/consul-template.zip -d "${CONSUL_TEMPLATE_INSTALL_DIR}/"
chmod u+x "${CONSUL_TEMPLATE_INSTALL_DIR}/consul-template"
ln -s "${CONSUL_TEMPLATE_INSTALL_DIR}/consul-template" "${SYMLINK_DIR}/consul-template"
chmod u+x "${SYMLINK_DIR}/consul-template"
rm /tmp/consul-template.zip
echo "Consul-Template version: $(consul-template --version)"

echo "4. Creating Consul configuration and data directories..."
mkdir -p "$CONSUL_CONFIG_DIR"
mkdir -p "$CONSUL_DATA_DIR"
chown -R ${USER:-$(whoami)}:$USER "$CONSUL_DATA_DIR"

echo "4.1. Creating configuration file for Consul Server..."
cat <<EOF | tee "$CONSUL_CONFIG_DIR/server.hcl"
# server.hcl
data_dir = "$CONSUL_DATA_DIR"
server = true
bootstrap_expect = 1 # Single development server
client_addr = "0.0.0.0" # Allows access from any IP
bind_addr = "$LOCAL_IP" # Consul listens on this interface
ui = true # Enable the user interface
EOF

echo "4.2. Creating systemd unit for Consul Server..."
cat <<EOF | tee /etc/systemd/system/consul.service
[Unit]
Description="HashiCorp Consul - A service mesh solution"
Documentation=https://www.consul.io/
Requires=network-online.target
After=network-online.target

[Service]
ExecStart=${SYMLINK_DIR}/consul agent -config-dir=${CONSUL_CONFIG_DIR}
ExecReload=${SYMLINK_DIR}/consul reload
KillMode=process
Restart=on-failure
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

echo "5. Starting and enabling Consul Server..."
systemctl daemon-reload
systemctl start consul
systemctl enable consul
echo "Consul Server Status:"
systemctl status consul --no-pager

echo "6. Installing HAProxy..."
apt install haproxy -y

echo "6.3. Creating HAProxy template file ($HAPROXY_TEMPLATE_FILE)..."
cat <<EOF | tee "$HAPROXY_TEMPLATE_FILE"
global
    log /dev/log    local0 notice
    chroot /var/lib/haproxy
    stats socket /run/haproxy/admin.sock mode 660 level admin expose-fd listeners
    stats timeout 30s
    user haproxy
    group haproxy
    daemon

defaults
    log     global
    mode    http
    option  httplog
    option  dontlognull
    timeout connect 5000ms
    timeout client  50000ms
    timeout server  50000ms

frontend my_webapp
    bind *:80
    mode http
    default_backend webservers

backend webservers
    mode http
    balance roundrobin
    {{- range service "webserver" }}
    server {{ .ID }} {{ .Address }}:{{ .Port }} check
    {{- end }}

listen stats
    bind *:8080
    stats enable
    stats uri /haproxy_stats
    stats realm Haproxy\\ Statistics
    stats auth admin:password
    stats refresh 10s
EOF

echo "7. Creating systemd unit for Consul-Template..."
cat <<EOF | tee /etc/systemd/system/consul-template.service
[Unit]
Description=Consul Template for HAProxy
After=consul.service

[Service]
ExecStart=${SYMLINK_DIR}/consul-template -template "${HAPROXY_TEMPLATE_FILE}:${HAPROXY_OUTPUT_CONFIG_FILE}:systemctl reload haproxy" -consul-addr "${LOCAL_IP}:8500"
KillMode=process
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

echo "7.1. Starting and enabling Consul-Template..."
systemctl daemon-reload
systemctl start haproxy
systemctl enable haproxy
systemctl start consul-template
systemctl enable consul-template
echo "Consul-Template Status:"
systemctl status consul-template --no-pager


echo "8. Setting up locust"
sudo apt install python3-locust"

echo "--- Configuration complete! ---"
echo "Consul UI available at: http://${LOCAL_IP}:8500/ui"
echo "HAProxy is listening on port 80."
echo "HAProxy statistics available at: http://${LOCAL_IP}:8080/haproxy_stats"
echo "User: admin, Password: password (CHANGE THIS IN PRODUCTION!)"
echo "Run locust with locust -f wso/locustfile.py and visit http://0.0.0.0:8089/ for testing, place host address (192.168.1.xxx) in UI"