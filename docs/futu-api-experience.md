Futu OpenD API — integration notes
====================================

Read calls work without unlocking
----------------------------------
- `get_cash()` → `ctx.accinfo_query()`
- `get_positions()` → `ctx.position_list_query()`

These succeed immediately even when the trade account is locked.

Write calls require trade account unlock
------------------------------------------
- `ctx.place_order()` — hangs if trade account is locked
- `ctx.unlock_trade(password="")` — also hangs if not unlocked via GUI first

Unlock must be done in the OpenD GUI first (click unlock, enter trade PIN).
After that, `unlock_trade(password="")` returns immediately (no PW needed for
subsequent API calls in the same session).

Context creation blocks in certain environments
-----------------------------------------------
`OpenSecTradeContext(host, port)` works fine inside pytest-asyncio but hangs
when called from a plain script (inline `-c` or standalone `.py`). Root cause
is unclear — might be a threading / event-loop interaction in the Futu SDK.
Always test via pytest, not raw scripts.

Board lot sizes matter
----------------------
Hong Kong stocks have fixed board lots. Buying fewer shares than 1 lot fails:

    "The order you placed contains odd lot (less than 1 lot)"

Known lot sizes (HK stocks):
- HK.00700 (Tencent):  100 shares/lot
- HK.09988 (Alibaba):  100 shares/lot
- HK.01810 (Xiaomi):   200 shares/lot
- HK.00788 (China Tower):  1000 shares/lot
- HK.00123 (Yuexiu):   2000 shares/lot

US stocks on Futu typically have lot size = 1.

Paper trading fills at market price, not limit price
-------------------------------------------------------
When placing a limit order in `TrdEnv.SIMULATE`, the order fills at the
current market price, not the limit price you specify. For example:

    place_order(price=500.0, qty=100, code="HK.00700", ...)

filled at ~465.6 HKD/share (the market price at that time), not 500.

This means buy/sell round-trips don't perfectly cancel — you get a small
difference from the buy/sell market spread. Relax cash assertions to
account for this (e.g., allow 200 HKD drift for 100-share trades).

Polling mode is slow but reliable
----------------------------------
Default `poll_interval=2.0` means each poll cycle takes 2s. For testing,
use `poll_interval=0.5` to speed things up.

There is no "open" or "close" on the trade context
----------------------------------------------------
Unlike sockets or HTTP clients, `OpenSecTradeContext` has no explicit
open/close lifecycle in the broker code. The SDK manages connection
internally. This is fine for long-lived daemons but means stale
connections accumulate if you keep creating new contexts.

Markers for CI exclusion
--------------------------
Integration tests that need OpenD are tagged with `pytest.mark.futu`
and excluded from CI with `-m "not redis and not futu"`. The futu-api
package is optional (`pip install ".[futu]"`), so `importorskip("futu")`
provides a second safety net.
