#!/bin/sh

set -eu

REPO_URL="https://github.com/skoda-octavia/flask-service.git"
APP_DIR="/opt/flask_app"
FLASK_PORT=5000

HOST_ADDR="192.168.1.18"

VM_NETWORK_INTERFACE="eth0"

CONSUL_VERSION="1.16.2"
CONSUL_TEMPLATE_VERSION="0.31.0"
INSTALL_DIR="/usr/local/bin"
CONSUL_CONFIG_DIR="/etc/consul.d"
CONSUL_DATA_DIR="/opt/consul"

if [ "$(id -u)" -ne 0 ]; then
  echo "Proszę uruchom skrypt jako root (sudo)."
  exit 1
fi

mkdir -p "/var/log/consul"
mkdir -p "/var/log/flask_app"
mkdir -p "/var/log/consul-template-vm"

echo "--- Rozpoczynanie konfiguracji VM (Flask App i Consul Agent) - Alpine Linux ---"

echo "1. Aktualizacja indeksu pakietów i instalacja podstawowych pakietów..."
apk update
apk add --no-cache curl unzip git python3 py3-pip python3-dev py3-virtualenv openrc

echo "2. Instalacja Consul Agent..."
curl -fsSL https://releases.hashicorp.com/consul/${CONSUL_VERSION}/consul_${CONSUL_VERSION}_linux_amd64.zip -o /tmp/consul.zip
unzip /tmp/consul.zip -d "${INSTALL_DIR}/"
chmod +x "${INSTALL_DIR}/consul"
rm /tmp/consul.zip
echo "Consul Agent wersja: $(consul --version)"

echo "3. Instalacja Consul-Template na VM..."
curl -fsSL https://releases.hashicorp.com/consul-template/${CONSUL_TEMPLATE_VERSION}/consul-template_${CONSUL_TEMPLATE_VERSION}_linux_amd64.zip -o /tmp/consul-template.zip
unzip /tmp/consul-template.zip -d "${INSTALL_DIR}/"
chmod +x "${INSTALL_DIR}/consul-template"
rm /tmp/consul-template.zip
echo "Consul-Template VM wersja: $(consul-template --version)"

echo "4. Tworzenie katalogów konfiguracyjnych i danych dla Consul Agent..."
mkdir -p "$CONSUL_CONFIG_DIR"
mkdir -p "$CONSUL_DATA_DIR"
chown -R root:root "$CONSUL_DATA_DIR"

echo "5. Pobieranie adresu IP maszyny..."
VM_IP_ADDRESS=$(ip -4 addr show ${VM_NETWORK_INTERFACE} | grep -o '(?<=inet\s)\d+(\.\d+){3}' || ip addr show ${VM_NETWORK_INTERFACE} | grep 'inet ' | awk '{print $2}' | cut -d'/' -f1)
if [ -z "$VM_IP_ADDRESS" ]; then
    echo "Błąd: Nie udało się pobrać adresu IP dla interfejsu ${VM_NETWORK_INTERFACE}. Sprawdź nazwę interfejsu."
    exit 1
fi
echo "Pobrany adres IP VM: ${VM_IP_ADDRESS}"

echo "6. Konfiguracja Consul Agent (client.hcl)..."
CLIENT_HCL_CONTENT=$(cat <<EOF_CLIENT_HCL
data_dir = "$CONSUL_DATA_DIR"
bind_addr = "${VM_IP_ADDRESS}"
client_addr = "0.0.0.0"
retry_join = ["$HOST_ADDR"]
EOF_CLIENT_HCL
)
echo "${CLIENT_HCL_CONTENT}" > "${CONSUL_CONFIG_DIR}/client.hcl"

echo "7. Tworzenie skryptu init OpenRC dla Consul Agent..."
CONSUL_INIT_SCRIPT=$(cat <<'EOF_CONSUL_INIT'
#!/sbin/openrc-run

name="consul"
description="HashiCorp Consul - A service mesh solution (Agent)"

command="/usr/local/bin/consul"
command_args="agent -config-dir=/etc/consul.d"
command_background="yes"
pidfile="/run/${RC_SVCNAME}.pid"

output_log="/var/log/${RC_SVCNAME}/${RC_SVCNAME}.log"
error_log="/var/log/${RC_SVCNAME}/${RC_SVCNAME}.log"

depend() {
    need net
    after firewall
}

start_pre() {
    checkpath --directory --mode 0755 --owner root:root /run
}
EOF_CONSUL_INIT
)
echo "${CONSUL_INIT_SCRIPT}" > /etc/init.d/consul
chmod +x /etc/init.d/consul

echo "8. Uruchamianie i włączanie Consul Agent (początkowo, przed rejestracją usługi)..."
rc-update add consul default
rc-service consul start
echo "Consul Agent Status (initial):"
rc-service consul status

echo "9. Klonowanie repozytorium Flask i instalacja zależności..."
mkdir -p "$APP_DIR"
git clone "$REPO_URL" "$APP_DIR"
cd "$APP_DIR"
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate

echo "10. Tworzenie skryptu init OpenRC dla Flask app..."
FLASK_INIT_SCRIPT=$(cat <<EOF_FLASK_INIT
#!/sbin/openrc-run

name="flask_app"
description="Gunicorn instance to serve Flask App"

command="$APP_DIR/venv/bin/gunicorn"
command_args="--workers 4 --bind 0.0.0.0:$FLASK_PORT main:app"
command_background="yes"
pidfile="/run/\${RC_SVCNAME}.pid"

output_log="/var/log/\${RC_SVCNAME}/\${RC_SVCNAME}.log"
error_log="/var/log/\${RC_SVCNAME}/\${RC_SVCNAME}.log"

directory="$APP_DIR"
command_user="root"

depend() {
    need net
    after consul
}

start_pre() {
    checkpath --directory --mode 0755 --owner root:root /run
}
EOF_FLASK_INIT
)
echo "${FLASK_INIT_SCRIPT}" > /etc/init.d/flask_app
chmod +x /etc/init.d/flask_app

echo "11. Uruchamianie i włączanie Flask app..."
rc-update add flask_app default
rc-service flask_app start
echo "Flask App Status:"
rc-service flask_app status

echo "12. Tworzenie szablonu definicji usługi Flask dla Consula..."
FLASK_WEB_SERVICE_TMPL_CONTENT=$(cat <<EOF_FLASK_WEB_SERVICE_TMPL
{
  "service": {
    "id": "flask-app-$(hostname)",
    "name": "webserver",
    "tags": ["flask", "web"],
    "address": "${VM_IP_ADDRESS}",
    "port": $FLASK_PORT,
    "checks": [
      {
        "http": "http://${VM_IP_ADDRESS}:$FLASK_PORT/health",
        "interval": "10s",
        "timeout": "1s"
      }
    ]
  }
}
EOF_FLASK_WEB_SERVICE_TMPL
)
echo "${FLASK_WEB_SERVICE_TMPL_CONTENT}" > "${CONSUL_CONFIG_DIR}/flask_webserver.json.ctmpl"

echo "13. Konfiguracja i uruchomienie Consul-Template na VM..."
CONSUL_TEMPLATE_INIT_SCRIPT=$(cat <<EOF_CONSUL_TEMPLATE_INIT
#!/sbin/openrc-run

name="consul_template_vm"
description="Consul Template for Flask Service Registration"

command="/usr/local/bin/consul-template"
command_args="-template \"${CONSUL_CONFIG_DIR}/flask_webserver.json.ctmpl:${CONSUL_CONFIG_DIR}/flask_webserver.json:rc-service consul restart\" -consul-addr \"127.0.0.1:8500\""
command_background="yes"
pidfile="/run/\${RC_SVCNAME}.pid"

output_log="/var/log/\${RC_SVCNAME}/\${RC_SVCNAME}.log"
error_log="/var/log/\${RC_SVCNAME}/\${RC_SVCNAME}.log"

start_pre() {
    checkpath --directory --mode 0755 --owner root:root /run
}
EOF_CONSUL_TEMPLATE_INIT
)
echo "${CONSUL_TEMPLATE_INIT_SCRIPT}" > /etc/init.d/consul-template-vm
chmod +x /etc/init.d/consul-template-vm

echo "13.1. Uruchamianie i włączanie Consul-Template na VM..."
rc-update add consul-template-vm default
rc-service consul-template-vm start
echo "Consul-Template VM Status:"
rc-service consul-template-vm status

echo "--- Konfiguracja VM zakończona! ---"
echo "Aplikacja Flask nasłuchuje na porcie $FLASK_PORT."
echo "Consul Agent powinien dołączyć do serwera $HOST_ADDR."
echo "Usługa Flask zostanie zarejestrowana przez Consul-Template."
echo "Pamiętaj, aby otworzyć port $FLASK_PORT w firewallu VM (jeśli używasz iptables)."
