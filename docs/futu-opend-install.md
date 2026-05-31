# Install Futu OpenD (Rust version) on Ubuntu VPS

### 1. Download & Extract
```bash
cd /root
wget https://futuapi.com/releases/rs-v1.4.109/futu-opd-linux_x86_64-1.4.109.tar.gz
tar xzf futu-opd-linux_x86_64-1.4.109.tar.gz
mv futu-opd-linux_x86_64-1.4.109 futu-opend
cd futu-opend
chmod +x futu-opend futucli futu-mcp
```

### 2. First Login (SMS verification)
```bash
/root/futu-opend/futu-opend --login-account=14869779 --lang=en --ip=0.0.0.0 --port=11111 --reset-device
```
- Enter password (stored in `$HOME/.futu-opend-rs/credentials-*.json`)
- SMS code sent to phone; enter verification code
- Credentials are cached; subsequent runs don't need SMS

### 3. systemd Service
Create `/etc/systemd/system/futu-opend.service`:
```ini
[Unit]
Description=Futu OpenD Gateway
After=network.target

[Service]
ExecStart=/root/futu-opend/futu-opend --login-account=14869779 --lang=en --ip=0.0.0.0 --port=11111
Restart=on-failure
RestartSec=10
User=root

[Install]
WantedBy=multi-user.target
```

Enable & start:
```bash
systemctl daemon-reload
systemctl enable futu-opend
systemctl start futu-opend
systemctl status futu-opend
```

### 4. Verify
- OpenD listens on `0.0.0.0:11111` (all interfaces)
- Python client connects via `futu.OpenSecTradeContext(host="127.0.0.1", port=11111)`
- Use `TrdEnv.SIMULATE` for paper trading, `TrdEnv.REAL` for production
- Test connectivity: `python -c "from futu import OpenSecTradeContext; ctx = OpenSecTradeContext(host='127.0.0.1', port=11111); print('OK')"`

### Notes
- Rust version (v1.4.109+) replaced classic C++ version - same API, better performance
- Binaries: `futu-opend` (gateway), `futucli` (CLI), `futu-mcp` (MCP server)
- Python package: `pip install futu-api`
- Paper trading starts with $0.00 - fund via Futu app's paper trading account
