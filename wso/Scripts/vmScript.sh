#!/bin/bash

REPO_URL="https://github.com/skoda-octavia/flask-service.git"
APP_DIR="/opt/flask_app"
FLASK_PORT=5000

HOST_ADDR="192.168.1.130"

VM_NETWORK_INTERFACE="enp0s3"

CONSUL_VERSION="1.16.2"
CONSUL_TEMPLATE_VERSION="0.31.0"
INSTALL_DIR="/usr/local/bin"
CONSUL_CONFIG_DIR="/etc/consul.d"
CONSUL_DATA_DIR="/opt/consul"

if [ "$EUID" -ne 0 ]; then
  echo "Proszę uruchom skrypt jako root (sudo)."
  exit 1
fi

echo "--- Rozpoczynanie konfiguracji VM (Flask App i Consul Agent) ---"

echo "1. Instalacja podstawowych pakietów i zależności Python..."
apt update -y
apt install -y curl unzip git python3 python3-pip python3-venv systemd net-tools

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
VM_IP_ADDRESS=$(ip -4 addr show ${VM_NETWORK_INTERFACE} | grep -oP '(?<=inet\s)\d+(\.\d+){3}')
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
echo "${CLIENT_HCL_CONTENT}" | sudo tee "${CONSUL_CONFIG_DIR}/client.hcl" > /dev/null


echo "7. Tworzenie jednostki systemd dla Consul Agent..."
CONSUL_SERVICE_CONTENT=$(cat <<EOF_CONSUL_SERVICE
[Unit]
Description="HashiCorp Consul - A service mesh solution (Agent)"
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
EOF_CONSUL_SERVICE
)
echo "${CONSUL_SERVICE_CONTENT}" | sudo tee /etc/systemd/system/consul.service > /dev/null


echo "8. Uruchamianie i włączanie Consul Agent (początkowo, przed rejestracją usługi)..."
systemctl daemon-reload
systemctl start consul
systemctl enable consul
echo "Consul Agent Status (initial):"
systemctl status consul --no-pager


echo "9. Klonowanie repozytorium Flask i instalacja zależności..."
mkdir -p "$APP_DIR"
git clone "$REPO_URL" "$APP_DIR"
cd "$APP_DIR"
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate


echo "10. Tworzenie jednostki systemd dla Flask app..."
FLASK_SERVICE_CONTENT=$(cat <<EOF_FLASK_SERVICE
[Unit]
Description=Gunicorn instance to serve Flask App
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/gunicorn --workers 4 --bind 0.0.0.0:$FLASK_PORT app:app
Restart=always
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF_FLASK_SERVICE
)
echo "${FLASK_SERVICE_CONTENT}" | sudo tee /etc/systemd/system/flask_app.service > /dev/null


echo "11. Uruchamianie i włączanie Flask app..."
systemctl daemon-reload
systemctl start flask_app
systemctl enable flask_app
echo "Flask App Status:"
systemctl status flask_app --no-pager


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
echo "${FLASK_WEB_SERVICE_TMPL_CONTENT}" | sudo tee "${CONSUL_CONFIG_DIR}/flask_webserver.json.ctmpl" > /dev/null


echo "13. Konfiguracja i uruchomienie Consul-Template na VM..."
CONSUL_TEMPLATE_VM_SERVICE_CONTENT=$(cat <<EOF_CONSUL_TEMPLATE_VM_SERVICE
[Unit]
Description=Consul Template for Flask Service Registration
After=consul.service

[Service]
# Environment="VM_IP_ADDRESS=${VM_IP_ADDRESS}" # To już niepotrzebne, bo IP jest w .ctmpl
ExecStart=${INSTALL_DIR}/consul-template -template "${CONSUL_CONFIG_DIR}/flask_webserver.json.ctmpl:${CONSUL_CONFIG_DIR}/flask_webserver.json:sudo consul reload" -consul-addr "127.0.0.1:8500"
KillMode=process
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF_CONSUL_TEMPLATE_VM_SERVICE
)
echo "${CONSUL_TEMPLATE_VM_SERVICE_CONTENT}" | sudo tee /etc/systemd/system/consul-template-vm.service > /dev/null


echo "13.1. Uruchamianie i włączanie Consul-Template na VM..."
systemctl daemon-reload
systemctl start consul-template-vm
systemctl enable consul-template-vm
echo "Consul-Template VM Status:"
systemctl status consul-template-vm --no-pager

echo "--- Konfiguracja VM zakończona! ---"
echo "Aplikacja Flask nasłuchuje na porcie $FLASK_PORT."
echo "Consul Agent powinien dołączyć do serwera $HOST_ADDR."
echo "Usługa Flask zostanie zarejestrowana przez Consul-Template."
echo "Pamiętaj, aby otworzyć port $FLASK_PORT w firewallu VM (jeśli używasz UFW)."