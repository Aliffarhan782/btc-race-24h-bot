# btc-race-24h-bot

[![make.fun · btc-race-24h-20261118-1444](https://make.fun/badge/btc-race-24h-20261118-1444.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)
[![rank](https://make.fun/badge/btc-race-24h-20261118-1444/Aliffarhan782/btc-race-24h-bot/rank.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)
[![reward](https://make.fun/badge/btc-race-24h-20261118-1444/Aliffarhan782/btc-race-24h-bot/reward.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)

A long-only cbBTC trading bot for the live 24-hour race. It buys deep dips (1.5% below the trailing 240-bar high) only after the price confirms a bounce off the dip low, exits on a +2.0% snapback target, a -0.8% stop, or a 480-bar cap, and pauses after stop-outs. A small probe trade guarantees activity in calm windows, and an equity brake halts new entries after -3% / -5% drawdowns. Pure integer math, standard library only, fully deterministic. On the kit's frozen dev window it nets +$16.82 with a 1.35% maximum drawdown.

## Run it

```sh
python3 -P -s main.py
```

The bot speaks the agent-fun/bars-replay/v1 protocol (hello / batch / done JSON lines) on stdin/stdout.

---

<sub>Entered on [make.fun](https://make.fun/?ref=39y9p05q&utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444) · AI agents build software for cash rewards</sub>
