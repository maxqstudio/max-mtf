from research.sample_policy import auto_trade_sample
from strategy.strategy_optimizer import optimizer_trade_sample
from models.model_lab import load_cfg

cfg=load_cfg("config.json")
expected_research={"M1":32,"M5":28,"M15":16,"M30":12,"H1":8,"H2":6,"H4":4,"D1":2}
expected_optimizer={"M1":80,"M5":70,"M15":40,"M30":29,"H1":20,"H2":15,"H4":10,"D1":5}
for tf,rate in expected_research.items():
    r=auto_trade_sample(tf,"2026-01-01","2026-02-01",cfg,"DISCOVERY")
    assert r["scaled_trades_per_month"]==rate,(tf,r)
    assert isinstance(r["scaled_trades_per_month"],int) and isinstance(r["minimum_trades"],int),r
    assert r["rounding"]=="CEIL_MONTHLY_RATE_AND_FINAL_REQUIREMENT",r
for tf,rate in expected_optimizer.items():
    r=optimizer_trade_sample(tf,"2026.01.01","2026.02.01")
    assert r["scaled_trades_per_month"]==rate,(tf,r)
    assert isinstance(r["scaled_trades_per_month"],int) and isinstance(r["minimum_trades"],int),r
# Exact evaluated duration remains prorated after the integer monthly-rate resolution.
a=auto_trade_sample("H1","2020-01-01","2022-12-31",cfg,"DISCOVERY")
assert a["base_h1_trades_per_month"]==8 and a["minimum_trades"]==288,a
# Exposure-aware WFA/CPCV sampling is still supported and the final requirement remains integer.
b=auto_trade_sample("H1","2020-01-01","2022-12-31",cfg,"DISCOVERY",observed_fraction=0.50)
assert b["minimum_trades"]==144,b
print("AUTO_TRADE_SAMPLE_V076_SELFTEST PASS",a["minimum_trades"],b["minimum_trades"])
