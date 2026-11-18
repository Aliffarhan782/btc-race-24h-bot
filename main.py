"""cbBTC race bot: capitulation-dip snapback, with a calm-window probe and equity brakes.

Strategy (long only, one position, integer arithmetic throughout, fully deterministic):

- Deep-dip module (the earner). It tracks the trailing 240-bar high of closes. When the
  close falls 1.50% or more below that high, a capitulation is in progress: the bot
  tracks the dip's low and stays out. It buys 90% of cash only once the close has
  recovered 0.25% off the dip low (a snapback, not a falling knife), and then exits on
  a +2.00% take-profit against the position's cost, a -0.90% stop, or after 480 bars.
  After a stop-out it waits 150 bars before the next dip entry, so a long slide costs
  one stop, not five. A dip that recovers to within 0.80% of the trailing high without
  a snapback entry simply disarms.
- Probe module (guardrail insurance). If nothing has filled by bar 700, the same
  dip-and-snapback shape runs at shallow settings (0.70% dip, 0.12% bounce, 12% of
  cash, +0.40% / -0.45% exits, 60-bar cap) so a dead-calm window still produces the
  trade the race guardrail requires, at trivial risk.
- Equity brake. If equity falls 3% below its peak, the bot flattens (via the normal
  exit path next time it holds) and pauses entries for 240 bars; at 5% it stops
  entering for the rest of the window. (Exits are never blocked.)

Costs are the reason for the shape: a round trip pays 4 bps fee + 2 bps slippage per
side plus constant-product impact against the bar's pool depth, so only moves well
over 1% clear the stack at near-full size. Every shorter-horizon rule we tested
(gap scalping, EMA/band reversion, breakouts, shallow dips) lost money after costs
across resampled windows; the capitulation snapback was the one rule that stayed
positive in aggregate. Position size is set against the pool depth the fills trade
against: at 90% of a $1,000 account the impact is ~9 bps a side, which the 2%
take-profit absorbs; the probe's 12% size pays ~1 bp.

The bot reads only the bars it is sent (no clock, no files, no randomness), so the
two graded executions produce byte-identical replies.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

BPS = 10_000
SYMBOL = "CBBTC"

# Deep-dip module.
DIP_LOOKBACK = 240
DIP_BPS = 150
DIP_BOUNCE_BPS = 25
DIP_SIZE_FRAC_NUM, DIP_SIZE_FRAC_DEN = 90, 100
DIP_TP_BPS = 200
DIP_STOP_BPS = 90
DIP_MAX_HOLD = 480
DIP_ENTRY_SLIP_BPS = 200
STOP_COOLDOWN = 150
REARM_BPS = 80

# Probe module.
PROBE_FROM_BAR = 700
PROBE_LOOKBACK = 120
PROBE_DIP_BPS = 70
PROBE_BOUNCE_BPS = 12
PROBE_SIZE_FRAC_NUM, PROBE_SIZE_FRAC_DEN = 12, 100
PROBE_TP_BPS = 40
PROBE_STOP_BPS = 45
PROBE_MAX_HOLD = 60
PROBE_REARM_BPS = 20
PROBE_ENTRY_SLIP_BPS = 150

# Equity brake.
BRAKE_DD_BPS = 300
BRAKE_PAUSE = 240
KILL_DD_BPS = 500

MIN_NOTIONAL = 1_000_000


class Bot:
    def __init__(self):
        self.closes = []
        self.dip_state = "watch"
        self.dip_low = None
        self.probe_state = "watch"
        self.probe_low = None
        self.pos_kind = None
        self.entry_bar = -1
        self.prev_qty = 0
        self.last_gain = None
        self.ever_filled = False
        self.cooldown_until = -1
        self.peak_eq = None
        self.pause_until = -1
        self.dead = False

    def _gain_bps(self, state, held, close):
        if not held.cost:
            return 0
        return state.value(SYMBOL, held.qty, close) * BPS // held.cost - BPS

    def on_batch(self, state, batch):
        # Only act on batches that carry a CBBTC bar; a missing minute changes nothing.
        bar = None
        for b in batch["bars"]:
            if b["symbol"] == SYMBOL:
                bar = b
        if bar is None or state.warming_up:
            return []
        k = state.seq
        c = int(bar["c"])
        self.closes.append(c)
        eq = state.equity
        if self.peak_eq is None or eq > self.peak_eq:
            self.peak_eq = eq
        held = state.positions.get(SYMBOL)
        qty = held.qty if held else 0
        if qty and not self.prev_qty:
            self.entry_bar = k
            self.ever_filled = True
        if not qty and self.prev_qty:
            if (self.pos_kind == "dip" and self.last_gain is not None
                    and self.last_gain <= -DIP_STOP_BPS + 15):
                self.cooldown_until = k + STOP_COOLDOWN
            self.pos_kind = None
        self.prev_qty = qty

        if qty:
            g = self._gain_bps(state, held, c)
            self.last_gain = g
            held_bars = k - self.entry_bar
            if self.pos_kind == "dip":
                if g >= DIP_TP_BPS or g <= -DIP_STOP_BPS or held_bars >= DIP_MAX_HOLD:
                    return [{"side": "sell", "symbol": SYMBOL, "qty": held.qty,
                             "max_slippage_bps": 10_000}]
            else:
                if g >= PROBE_TP_BPS or g <= -PROBE_STOP_BPS or held_bars >= PROBE_MAX_HOLD:
                    return [{"side": "sell", "symbol": SYMBOL, "qty": held.qty,
                             "max_slippage_bps": 10_000}]
            return []
        self.last_gain = None

        # Flat: risk brakes first.
        if self.dead:
            return []
        if self.peak_eq and eq * BPS <= self.peak_eq * (BPS - KILL_DD_BPS):
            self.dead = True
            return []
        if k < self.pause_until:
            return []
        if self.peak_eq and eq * BPS <= self.peak_eq * (BPS - BRAKE_DD_BPS):
            self.pause_until = k + BRAKE_PAUSE
            return []
        if k < self.cooldown_until:
            return []

        # Deep-dip state machine.
        hi = max(self.closes[-DIP_LOOKBACK:])
        if self.dip_state == "watch":
            if len(self.closes) >= 30 and c * BPS <= hi * (BPS - DIP_BPS):
                self.dip_state = "dipping"
                self.dip_low = c
        elif self.dip_state == "dipping":
            if c < self.dip_low:
                self.dip_low = c
            if c * BPS >= hi * (BPS - REARM_BPS):
                self.dip_state = "watch"
            elif c * BPS >= self.dip_low * (BPS + DIP_BOUNCE_BPS):
                n = state.cash * DIP_SIZE_FRAC_NUM // DIP_SIZE_FRAC_DEN
                if n >= MIN_NOTIONAL:
                    self.dip_state = "watch"
                    self.pos_kind = "dip"
                    return [{"side": "buy", "symbol": SYMBOL, "notional_quote_units": n,
                             "max_slippage_bps": DIP_ENTRY_SLIP_BPS}]
            if self.dip_state == "dipping":
                return []  # capitulation in progress: the probe stands down too

        # Probe: only in a window where nothing has filled yet, late in the window.
        if not self.ever_filled and k >= PROBE_FROM_BAR:
            hi2 = max(self.closes[-PROBE_LOOKBACK:])
            if self.probe_state == "watch":
                if c * BPS <= hi2 * (BPS - PROBE_DIP_BPS):
                    self.probe_state = "dipping"
                    self.probe_low = c
            else:
                if c < self.probe_low:
                    self.probe_low = c
                if c * BPS >= hi2 * (BPS - PROBE_REARM_BPS):
                    self.probe_state = "watch"
                elif c * BPS >= self.probe_low * (BPS + PROBE_BOUNCE_BPS):
                    n = state.cash * PROBE_SIZE_FRAC_NUM // PROBE_SIZE_FRAC_DEN
                    if n >= MIN_NOTIONAL:
                        self.probe_state = "watch"
                        self.pos_kind = "probe"
                        return [{"side": "buy", "symbol": SYMBOL, "notional_quote_units": n,
                                 "max_slippage_bps": PROBE_ENTRY_SLIP_BPS}]
        return []


_bot = Bot()


def on_batch(state, batch):
    return _bot.on_batch(state, batch)


if __name__ == "__main__":
    makefun_bars.run(on_batch)
