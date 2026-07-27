# Averaging Entry Price: Known Limitations

## Current Behavior

When buying the same stock multiple times, `PositionStore.open_position` merges the
positions and calculates a **weighted average entry price**. Both SL and TP use this
average as the reference price.

```
Buy 1: 50sh @ $100
Buy 2: 50sh @ $200
Average: $150
SL (5%):  $142.50
TP (10%): $165.00
```

## The Problem

The two lots have very different risk profiles:

| Lot | Entry | P&L at SL ($142.50) | P&L at TP ($165) |
|-----|-------|---------------------|-------------------|
| 1   | $100  | -42.5%              | +65%              |
| 2   | $200  | -28.75%             | -17.5%            |

At the SL trigger, lot 1 is down 42.5% — far worse than the intended 5% risk.

At the TP trigger, lot 2 is still down 17.5% — not a real profit.

## Why Not Use Lot-Based SL/TP?

The obvious fix is SL/TP per lot:

```
Lot 1: SL=$95,  TP=$110
Lot 2: SL=$190, TP=$220
```

This is accurate but adds significant complexity:

- `PositionStore` needs to track multiple entries per symbol (or an `entries[]` array)
- `PriceMonitor` needs to evaluate multiple SL/TP levels per symbol
- Partial exits (sell lot 1, keep lot 2) require position splitting
- Reporting and reconciliation become harder

## Alternatives Considered

| Approach | SL basis | TP basis | Pros | Cons |
|----------|----------|----------|------|------|
| **Average** (current) | avg entry | avg entry | Simple, balanced | Dangerous when entries differ widely |
| **Worst entry** | highest entry | highest entry | Protects expensive lot, all lots profit at TP | Harder to hit TP, lot 1 sits in profit |
| **Best entry** | lowest entry | lowest entry | Easy TP, loose SL | Expensive lot takes big losses before SL |
| **Tiered exits** | per lot | per lot | Accurate | Very complex, partial position management |

## Recommendation

For entries at similar prices (within 10-20%), average entry is fine.

For entries at very different prices (2x+), consider:

1. **Block additional buys** if already holding (original behavior)
2. **Only buy if new price < current entry** (improves average, reduces risk)
3. **Implement tiered exits** (full solution, higher complexity)

## Implementation Notes

- `PositionStore.open_position` merges qty and averages entry price
- `TradingLogic.check_stop_loss` uses `pos.entry_price` (average)
- `TradingLogic.check_take_profit` uses `pos.entry_price` (average)
- `PriceMonitor` reads entry price from store on each cycle
- `SentimentTrader` allows buying more when already holding (average in)
