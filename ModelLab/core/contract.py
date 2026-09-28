FEATURES = [
    "ret1_atr", "ret3_atr", "ret6_atr", "fast_ma_gap_atr",
    "slow_ma_gap_atr", "fast_ma_slope_atr", "adx_scaled",
    "plus_di_scaled", "minus_di_scaled", "rsi_centered",
    "atr_percent", "atr_ratio", "bollinger_z", "bollinger_width_pct",
    "efficiency10", "candle_body_atr", "upper_wick_atr",
    "lower_wick_atr", "range_atr", "tick_volume_z", "hour_sin",
    "hour_cos", "weekday_sin", "weekday_cos", "trend_family",
    "range_family", "breakout_family", "pullback_family",
    "session_family", "shock_family", "relative_family", "rule_meta_score"
]

CLASS_NAMES = {0: "SELL", 1: "SKIP", 2: "BUY"}
CONTRACT_ID = "CP32_V1"

META_COLUMNS = [
    "contract", "signal_time", "decision_bar_time", "symbol", "period",
    "open", "high", "low", "close", "atr", "decision_bid", "decision_ask",
    "spread_points", "sl_atr", "tp_atr", "max_hold_bars", "consensus"
]

REQUIRED_COLUMNS = META_COLUMNS + FEATURES
