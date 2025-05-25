#!/bin/bash

CONSUL_VERSION="1.16.2"
CONSUL_TEMPLATE_VERSION="0.31.0"
INSTALL_DIR="/usr/local/bin"
CONSUL_CONFIG_DIR="/etc/consul.d"
CONSUL_DATA_DIR="/opt/consul"
HAPROXY_CONFIG_DIR="/etc/haproxy"
HAPROXY_TEMPLATE_FILE="$HAPROXY_CONFIG_DIR/haproxy.ctmpl"
HAPROXY_OUTPUT_CONFIG_FILE="$HAPROXY_CONFIG_DIR/haproxy.cfg"
HAPROXY_ERROR_PAGES_DIR="/etc/proxy-errors"

LOCAL_IP="127.0.0.1"

if [ "$EUID" -ne 0 ]; then
  echo "Please run the script as root (sudo)."
  exit 1
fi

echo "--- Starting Consul and Consul-Template Configuration ---"
echo "1. Updating package list and installing unzip, curl, git..."
apt update -y
apt install -y unzip curl git systemd

echo "2. Installing Consul (development server)..."
curl -fsSL https://releases.hashicorp.com/consul/${CONSUL_VERSION}/consul_${CONSUL_VERSION}_linux_amd64.zip -o /tmp/consul.zip
sudo unzip /tmp/consul.zip -d "${INSTALL_DIR}/"
sudo chmod +x "${INSTALL_DIR}/consul"
rm /tmp/consul.zip
echo "Consul version: $(consul --version)"

echo "3. Installing Consul-Template..."
curl -fsSL https://releases.hashicorp.com/consul-template/${CONSUL_TEMPLATE_VERSION}/consul-template_${CONSUL_TEMPLATE_VERSION}_linux_amd64.zip -o /tmp/consul-template.zip
sudo unzip /tmp/consul-template.zip -d "${INSTALL_DIR}/"
sudo chmod +x "${INSTALL_DIR}/consul-template"
rm /tmp/consul-template.zip
echo "Consul-Template version: $(consul-template --version)"

echo "4. Creating Consul configuration and data directories..."
sudo mkdir -p "$CONSUL_CONFIG_DIR"
sudo mkdir -p "$CONSUL_DATA_DIR"
sudo chown -R ${USER:-$(whoami)}:$USER "$CONSUL_DATA_DIR"

echo "4.1. Creating configuration file for Consul Server..."
cat <<EOF | sudo tee "$CONSUL_CONFIG_DIR/server.hcl"
# server.hcl
data_dir = "$CONSUL_DATA_DIR"
server = true
bootstrap_expect = 1 # Single development server
client_addr = "0.0.0.0" # Allows access from any IP
bind_addr = "$LOCAL_IP" # Consul listens on this interface
ui = true # Enable the user interface
EOF

echo "4.2. Creating systemd unit for Consul Server..."
cat <<EOF | sudo tee /etc/systemd/system/consul.service
[Unit]
Description="HashiCorp Consul - A service mesh solution"
Documentation=https://www.consul.io/
Requires=network-online.target
After=network-online.target

[Service]
ExecStart=${INSTALL_DIR}/consul agent -config-dir=${CONSUL_CONFIG_DIR}
ExecReload=${INSTALL_DIR}/consul reload
KillMode=process
Restart=on-failure
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

echo "5. Starting and enabling Consul Server..."
sudo systemctl daemon-reload
sudo systemctl start consul
sudo systemctl enable consul
echo "Consul Server Status:"
systemctl status consul --no-pager

echo "6. Installing HAProxy..."
sudo apt install haproxy -y

echo "6.3. Creating HAProxy template file ($HAPROXY_TEMPLATE_FILE)..."
cat <<EOF | sudo tee "$HAPROXY_TEMPLATE_FILE"
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
    server {{ .Node.Node }} {{ .Address }}:{{ .Port }} check
    {{- end }}

listen stats
    bind *:8080
    stats enable
    stats uri /haproxy_stats
    stats realm Haproxy\\ Statistics
    stats auth admin:password # CHANGE THIS PASSWORD IN PRODUCTION!
    stats refresh 10s
EOF

echo "7. Creating systemd unit for Consul-Template..."
cat <<EOF | sudo tee /etc/systemd/system/consul-template.service
[Unit]
Description=Consul Template for HAProxy
After=consul.service

[Service]
ExecStart=${INSTALL_DIR}/consul-template -template "${HAPROXY_TEMPLATE_FILE}:${HAPROXY_OUTPUT_CONFIG_FILE}:sudo systemctl reload haproxy" -consul-addr "${LOCAL_IP}:8500"
KillMode=process
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

echo "7.1. Starting and enabling Consul-Template..."
sudo systemctl daemon-reload
sudo systemctl start haproxy
sudo systemctl enable haproxy
sudo systemctl start consul-template
sudo systemctl enable consul-template
echo "Consul-Template Status:"
systemctl status consul-template --no-pager

echo "--- Configuration complete! ---"
echo "Consul UI available at: http://${LOCAL_IP}:8500/ui"
echo "HAProxy is listening on port 80."
echo "HAProxy statistics available at: http://${LOCAL_IP}:8080/haproxy_stats"
echo "User: admin, Password: password (CHANGE THIS IN PRODUCTION!)"
echo "Remember to add firewall rules to open ports 80, 8080, 8500 (TCP), and 8301 (UDP)!"
echo "On each virtual machine with the Flask service, run the 'setup_flask_vm.sh' script (with appropriate parameters)."