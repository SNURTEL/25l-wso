#!/bin/bash

REPO_URL="https://github.com/skoda-octavia/flask-service.git"
APP_DIR="/opt/flask_app"
FLASK_PORT=5000
HOST_ADDR=192.168.1.130

echo "1. Installing basic packages and Python dependencies..."
sudo apt update
sudo apt install -y curl unzip git python3 python3-pip python3-venv

echo "2. Installing Consul Agent..."
CONSUL_VERSION="1.16.2"
curl -fsSL https://releases.hashicorp.com/consul/${CONSUL_VERSION}/consul_${CONSUL_VERSION}_linux_amd64.zip -o /tmp/consul.zip
sudo unzip /tmp/consul.zip -d /usr/local/bin/
sudo chmod +x /usr/local/bin/consul
rm /tmp/consul.zip

echo "3. Creating Consul Agent configuration directory..."
sudo mkdir -p /etc/consul.d

# Zastąp dane!!!
echo "4. Configuring Consul Agent..."
cat <<EOF | sudo tee /etc/consul.d/client.hcl
data_dir = "/opt/consul"
bind_addr = "{{ GetInterfaceIP \"br0\" }}" # Zastąp "eth0"
client_addr = "0.0.0.0"
retry_join = ["$HOST_ADDR"] # Adres IP
EOF

echo "5. Cloning Flask repository and installing dependencies..."
sudo mkdir -p "$APP_DIR"
sudo git clone "$REPO_URL" "$APP_DIR"
cd "$APP_DIR"
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate

echo "6. Creating systemd service for Flask app..."
cat <<EOF | sudo tee /etc/systemd/system/flask_app.service
[Unit]
Description=Gunicorn instance to serve Flask App
After=network.target

[Service]
User=root # Możesz zmienić na mniej uprzywilejowanego użytkownika
Group=root # Możesz zmienić na mniej uprzywilejowaną grupę
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/gunicorn --workers 4 --bind 0.0.0.0:$FLASK_PORT app:app
Restart=always
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

echo "7. Starting and enabling Flask app..."
sudo systemctl daemon-reload
sudo systemctl start flask_app
sudo systemctl enable flask_app

echo "8. Registering Flask service with Consul..."
cat <<EOF | sudo tee /etc/consul.d/flask_webserver.json
{
  "service": {
    "id": "flask-app-$(hostname)",   # Unikalny ID usługi na tej maszynie
    "name": "webserver",             # Nazwa usługi dla HAProxy (musi być taka sama dla wszystkich instancji)
    "tags": ["flask", "web"],
    "address": "{{ GetInterfaceIP \"eth0\" }}", # Consul Agent automatycznie wypełni IP
    "port": $FLASK_PORT,
    "checks": [
      {
        "http": "http://{{ GetInterfaceIP \"eth0\" }}:$FLASK_PORT/health",
        "interval": "10s",
        "timeout": "1s"
      }
    ]
  }
}
EOF

echo "9. Creating systemd service for Consul Agent..."
cat <<EOF | sudo tee /etc/systemd/system/consul.service
[Unit]
Description="HashiCorp Consul - A service mesh solution"
Documentation=https://www.consul.io/
Requires=network-online.target
After=network-online.target

[Service]
ExecStart=/usr/local/bin/consul agent -config-dir=/etc/consul.d
ExecReload=/usr/local/bin/consul reload
KillMode=process
Restart=on-failure
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

echo "10. Starting and enabling Consul Agent..."
sudo systemctl daemon-reload
sudo systemctl start consul
sudo systemctl enable consul

echo "Flask app and Consul Agent configured and started successfully."
echo "Remember to open port $FLASK_PORT in firewall if applicable."