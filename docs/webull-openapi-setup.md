# Install Webull OpenAPI (Python SDK)

Webull exposes a sandbox/test environment for paper trading — the equivalent of
Futu's `TrdEnv.SIMULATE`. No local daemon is needed; the SDK talks HTTP directly.

### 1. Install the SDK

```bash
pip install webull-openapi-python-sdk
```

Or as a project extra:

```bash
pip install -e ".[webull]"
```

### 2. Get API credentials

- US: https://www.webull.com (OpenAPI Management)
- HK: https://www.webull.hk
- JP: https://www.webull.co.jp

Application review typically takes 1–2 business days.

### 3. Sandbox (paper) vs live

| Mode | Setting | Endpoint |
|------|---------|----------|
| Paper (default) | `WEBULL_REAL=false` | `api.sandbox.webull.com` |
| Live | `WEBULL_REAL=true` | `openapi.webull.com` |

Webull provides shared public test accounts for the sandbox (see the
[SDK docs](https://developer.webull.com/apis/docs/sdk) for current IDs). For a
dedicated test account, contact Webull support.

### 4. Verify setup

```bash
python -c "
from webull.core.client import ApiClient
from webull.trade.trade_client import TradeClient
api_client = ApiClient('<APP_KEY>', '<APP_SECRET>', 'us')
api_client.add_endpoint('us', 'api.sandbox.webull.com')
res = TradeClient(api_client).account_v2.get_account_list()
print(res.status_code, res.text[:200])
"
```

### 5. Configure EonTrading

```bash
# .env
BROKER=webull
WEBULL_APP_KEY=...
WEBULL_APP_SECRET=...
WEBULL_ACCOUNT_ID=...
# WEBULL_REAL=false   # paper by default; set true only for live
```

`WEBULL_REAL` defaults to `false` — the system starts in sandbox mode and never
touches real money unless you opt in.
