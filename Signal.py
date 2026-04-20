"""
IMC Signal Visualiser
=====================
Replays your algo's logic tick-by-tick against historical price data
and plots exactly where it would have placed buy/sell orders vs the mid price.

Usage:
    python signal_visualiser.py --files prices_day_-2.csv prices_day_-1.csv prices_day_0.csv
                                --product INTARIAN_PEPPER_ROOT
                                --day -2          (optional, default = all days)
                                --out chart.png   (optional, shows interactively if omitted)

Supported products (auto-detected from file):
    INTARIAN_PEPPER_ROOT, ASH_COATED_OSMIUM, TOMATOES, EMERALDS

Just drop your CSV price files into the same folder and run.
"""

import argparse
import math
import os
import sys
from dataclasses import dataclass, field
from typing import List, Optional

import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.ticker as mticker
import pandas as pd
import numpy as np


# ═══════════════════════════════════════════════════════════════════════════════
#  PASTE YOUR ALGO PARAMETERS HERE — keep in sync with your Trader class
# ═══════════════════════════════════════════════════════════════════════════════

class AlgoParams:
    # Emeralds
    EMERALD_FAIR_VAL    = 10000
    EMERALD_BID_OFFSET  = 3
    EMERALD_ASK_OFFSET  = 3
    EMERALD_LOT         = 10
    MAX_EMERALD_POS     = 20

    # Tomatoes
    MAX_TOMATO_POS      = 10
    TOMATO_WINDOW       = 50
    TOMATO_MIN_STD      = 5.0
    TOMATO_DEFAULT_MEAN = 4992.6
    TOMATO_DEFAULT_STD  = 21.13
    TOMATO_THRES_BUY    = 0.067582
    TOMATO_THRES_SELL   = 0.05
    TOMATO_CHEEKY_SCORE = 5

    # Ash Coated Osmium
    ASH_FAIR_VAL        = 10000
    ASH_BID_OFFSET      = 3
    ASH_ASK_OFFSET      = 3
    ASH_LOT             = 10
    MAX_ASH_POS         = 20

    # Intarian Pepper Root
    MAX_PEPPER_POS          = 20
    PEPPER_WINDOW           = 1000
    PEPPER_MIN_STD          = 5.0
    PEPPER_DEFAULT_MEAN     = 11000.0
    PEPPER_DEFAULT_STD      = 866.0
    PEPPER_THRES_BUY        = 0.05
    PEPPER_THRES_SELL       = 0.05
    PEPPER_CHEEKY_BUY_SCORE  = 0
    PEPPER_CHEEKY_SELL_SCORE = 15

    # Shared
    Z_ENTRY        = 0.8
    Z_STRONG       = 1.5
    OBI_GATE       = 0.0
    INVENTORY_SKEW = 0.5


# ═══════════════════════════════════════════════════════════════════════════════
#  SIGNAL ENGINE  — mirrors your Trader.run() logic exactly
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Tick:
    timestamp:   int
    mid:         float
    bid1:        float
    ask1:        float
    bid_vol1:    float
    ask_vol1:    float
    bid2:        float = 0.0
    ask2:        float = 0.0
    bid_vol2:    float = 0.0
    ask_vol2:    float = 0.0
    day:         int   = 0


@dataclass
class Signal:
    timestamp: int
    mid:       float
    price:     float
    side:      str    # "BUY" or "SELL"
    qty:       int
    reason:    str    # e.g. "z-score", "passive", "market-making"


def _obi(bid_vol, ask_vol) -> float:
    total = bid_vol + ask_vol
    return (bid_vol - ask_vol) / total if total > 0 else 0.0


def _rolling_stats(prices, default_mean, default_std, min_std):
    n = len(prices)
    if n == 0:
        return default_mean, default_std
    mean = sum(prices) / n
    if n < 2:
        return mean, default_std
    variance = sum((p - mean) ** 2 for p in prices) / (n - 1)
    std = math.sqrt(variance) if variance > 0 else default_std
    return mean, max(std, min_std)


def compute_signals(ticks: List[Tick], product: str) -> List[Signal]:
    """
    Replay the algo against each tick and record every order it would place.
    Edit the blocks below to match exactly what your Trader.run() does.
    """
    p = AlgoParams()
    signals: List[Signal] = []
    pos = 0
    prices_hist: List[float] = []

    for tk in ticks:
        mid = tk.mid
        obi1 = _obi(tk.bid_vol1, tk.ask_vol1)
        obi2 = _obi(tk.bid_vol2, tk.ask_vol2)

        # ── EMERALDS ────────────────────────────────────────────────────────
        if product == "EMERALDS":
            fair = p.EMERALD_FAIR_VAL
            if mid != fair:
                skew = int(round(fair - mid))
                my_bid = fair - p.EMERALD_BID_OFFSET + skew
                my_ask = fair + p.EMERALD_ASK_OFFSET + skew
                my_bid = min(my_bid, fair - 1)
                my_ask = max(my_ask, fair + 1)
            else:
                my_bid = fair - p.EMERALD_BID_OFFSET
                my_ask = fair + p.EMERALD_ASK_OFFSET

            inv_skew = -int(round(pos * 0.1))
            my_bid += inv_skew
            my_ask += inv_skew

            buy_room  = p.MAX_EMERALD_POS - pos
            sell_room = p.MAX_EMERALD_POS + pos
            bid_qty   = min(p.EMERALD_LOT, max(buy_room, 0))
            ask_qty   = min(p.EMERALD_LOT, max(sell_room, 0))

            # Sanity check (from your code: never buy above fair, sell below)
            if bid_qty > 0 and my_bid < fair:
                signals.append(Signal(tk.timestamp, mid, my_bid, "BUY",  bid_qty, "market-making"))
            if ask_qty > 0 and my_ask > fair:
                signals.append(Signal(tk.timestamp, mid, my_ask, "SELL", ask_qty, "market-making"))

        # ── TOMATOES ────────────────────────────────────────────────────────
        elif product == "TOMATOES":
            prices_hist.append(mid)
            prices_hist = prices_hist[-p.TOMATO_WINDOW:]
            if len(prices_hist) >= 5:
                t_mean, t_std = _rolling_stats(prices_hist, p.TOMATO_DEFAULT_MEAN,
                                               p.TOMATO_DEFAULT_STD, p.TOMATO_MIN_STD)
            else:
                t_mean, t_std = p.TOMATO_DEFAULT_MEAN, p.TOMATO_DEFAULT_STD

            # Take-liquidity on asks
            ask_price = tk.ask1
            z_ask = (ask_price - t_mean) / t_std
            if z_ask <= -p.TOMATO_THRES_BUY:
                buy_qty = min(int(tk.ask_vol1), p.MAX_TOMATO_POS - pos)
                if buy_qty > 0 and ask_price < t_mean:   # sanity check
                    signals.append(Signal(tk.timestamp, mid, ask_price, "BUY", buy_qty, "z-score"))
                    pos += buy_qty

            # Take-liquidity on bids
            bid_price = tk.bid1
            z_bid = (bid_price - t_mean) / t_std
            if z_bid >= p.TOMATO_THRES_SELL:
                sell_qty = min(int(tk.bid_vol1), p.MAX_TOMATO_POS + pos)
                if sell_qty > 0 and bid_price > t_mean:  # sanity check
                    signals.append(Signal(tk.timestamp, mid, bid_price, "SELL", sell_qty, "z-score"))
                    pos -= sell_qty

            # Passive cheeky quotes (always posted)
            buy_qty  = p.MAX_TOMATO_POS - pos
            sell_qty = p.MAX_TOMATO_POS + pos
            cheeky_bid = p.TOMATO_CHEEKY_SCORE - 5
            cheeky_ask = p.TOMATO_CHEEKY_SCORE + 5
            if buy_qty > 0:
                signals.append(Signal(tk.timestamp, mid, cheeky_bid,  "BUY",  buy_qty,  "passive"))
            if sell_qty > 0:
                signals.append(Signal(tk.timestamp, mid, cheeky_ask, "SELL", sell_qty, "passive"))

        # ── ASH_COATED_OSMIUM ───────────────────────────────────────────────
        elif product == "ASH_COATED_OSMIUM":
            fair    = p.ASH_FAIR_VAL
            my_bid  = fair - p.ASH_BID_OFFSET
            my_ask  = fair + p.ASH_ASK_OFFSET
            buy_room  = p.MAX_ASH_POS - pos
            sell_room = p.MAX_ASH_POS + pos
            bid_qty = min(p.ASH_LOT, max(buy_room, 0))
            ask_qty = min(p.ASH_LOT, max(sell_room, 0))

            if bid_qty > 0 and obi1 > p.OBI_GATE:
                signals.append(Signal(tk.timestamp, mid, my_bid, "BUY",  bid_qty, "market-making"))
            if ask_qty > 0 and obi1 < -p.OBI_GATE:
                signals.append(Signal(tk.timestamp, mid, my_ask, "SELL", ask_qty, "market-making"))

        # ── INTARIAN_PEPPER_ROOT ─────────────────────────────────────────────
        elif product == "INTARIAN_PEPPER_ROOT":
            prices_hist.append(mid)
            prices_hist = prices_hist[-p.PEPPER_WINDOW:]

            # Trend fair value: base + timestamp * slope
            day_bases = {-2: 10000.0, -1: 11000.0, 0: 12000.0}
            slope = 1000 / 999900.0
            fair = day_bases.get(tk.day, 10000.0) + tk.timestamp * slope

            resid = mid - fair
            buy_room  = p.MAX_PEPPER_POS - pos
            sell_room = p.MAX_PEPPER_POS + pos

            # Mean-reversion on residual
            if resid < -6 and buy_room > 0:
                signals.append(Signal(tk.timestamp, mid, tk.ask1, "BUY",
                                      min(buy_room, 5), "resid<-6"))
            elif resid > 6 and sell_room > 0:
                signals.append(Signal(tk.timestamp, mid, tk.bid1, "SELL",
                                      min(sell_room, 5), "resid>+6"))

            # Market-make around trend fair value
            bid_price = int(fair) - p.PEPPER_CHEEKY_BUY_SCORE
            ask_price = int(fair) + p.PEPPER_CHEEKY_SELL_SCORE
            if buy_room > 0 and obi1 > 0:
                signals.append(Signal(tk.timestamp, mid, bid_price, "BUY",
                                      min(buy_room, p.MAX_PEPPER_POS), "passive"))
            if sell_room > 0 and obi1 < 0:
                signals.append(Signal(tk.timestamp, mid, ask_price, "SELL",
                                      min(sell_room, p.MAX_PEPPER_POS), "passive"))

    return signals


# ═══════════════════════════════════════════════════════════════════════════════
#  DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════════

def load_ticks(csv_paths: List[str], product: str,
               day_filter: Optional[int] = None) -> List[Tick]:
    frames = []
    for path in csv_paths:
        try:
            df = pd.read_csv(path, sep=";")
            frames.append(df)
        except Exception as e:
            print(f"Warning: could not read {path}: {e}")

    if not frames:
        sys.exit("No price files could be loaded.")

    df = pd.concat(frames).reset_index(drop=True)
    df = df[df["product"] == product].copy()

    if df.empty:
        available = df["product"].unique() if not df.empty else "unknown"
        sys.exit(f"Product '{product}' not found. Available: {available}")

    if day_filter is not None:
        df = df[df["day"] == day_filter]
        if df.empty:
            sys.exit(f"No data for day={day_filter}.")

    df = df.sort_values(["day", "timestamp"]).reset_index(drop=True)
    df = df[df["mid_price"] > 0]

    def safe(col):
        return pd.to_numeric(df.get(col, 0), errors="coerce").fillna(0)

    ticks = []
    for _, row in df.iterrows():
        ticks.append(Tick(
            timestamp = int(row["timestamp"]),
            mid       = float(row["mid_price"]),
            bid1      = float(row.get("bid_price_1", 0) or 0),
            ask1      = float(row.get("ask_price_1", 0) or 0),
            bid_vol1  = float(row.get("bid_volume_1", 0) or 0),
            ask_vol1  = float(row.get("ask_volume_1", 0) or 0),
            bid2      = float(row.get("bid_price_2", 0) or 0),
            ask2      = float(row.get("ask_price_2", 0) or 0),
            bid_vol2  = float(row.get("bid_volume_2", 0) or 0),
            ask_vol2  = float(row.get("ask_volume_2", 0) or 0),
            day       = int(row["day"]),
        ))
    return ticks


# ═══════════════════════════════════════════════════════════════════════════════
#  PLOTTING
# ═══════════════════════════════════════════════════════════════════════════════

BG     = "#fafafa"
PANEL  = "white"
GRID   = "#ebebeb"
C_MID  = "#185FA5"
C_FAIR = "#888888"
C_BUY  = "#1D9E75"
C_SELL = "#D85A30"
REASON_COLORS = {
    "z-score":      ("#1D9E75", "#D85A30"),
    "market-making":("#0F6E56", "#993C1D"),
    "passive":      ("#9FE1CB", "#F5C4B3"),
    "resid<-6":     ("#1D9E75", "#1D9E75"),
    "resid>+6":     ("#D85A30", "#D85A30"),
}


def style(ax, title=""):
    ax.set_facecolor(PANEL)
    ax.grid(True, color=GRID, lw=0.6, zorder=0)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#ccc")
    ax.tick_params(colors="#555", labelsize=8)
    if title:
        ax.set_title(title, fontsize=10, color="#333", pad=8, fontweight="normal")


def plot(ticks: List[Tick], signals: List[Signal], product: str,
         day_filter: Optional[int], out: Optional[str]):

    timestamps = [t.timestamp for t in ticks]
    mids       = [t.mid for t in ticks]

    # Separate signals by reason category
    reason_groups = {}
    for s in signals:
        reason_groups.setdefault(s.reason, []).append(s)

    # Compute fair value line if applicable
    fair_line = None
    if product == "INTARIAN_PEPPER_ROOT":
        day_bases  = {-2: 10000.0, -1: 11000.0, 0: 12000.0}
        slope      = 1000 / 999900.0
        fair_line  = [day_bases.get(t.day, 10000.0) + t.timestamp * slope for t in ticks]
    elif product in ("EMERALDS", "ASH_COATED_OSMIUM"):
        fair_line = [10000.0] * len(ticks)

    # Compute residual for pepper
    show_residual = (product == "INTARIAN_PEPPER_ROOT" and fair_line is not None)

    n_rows = 3 if show_residual else 2
    fig = plt.figure(figsize=(14, 4 + n_rows * 3.5), facecolor=BG)
    day_label = f"day {day_filter}" if day_filter is not None else "all days"
    fig.suptitle(f"{product}  —  signal sanity check  ({day_label})",
                 fontsize=13, fontweight="normal", color="#222", y=0.99)
    gs = gridspec.GridSpec(n_rows, 1, figure=fig, hspace=0.45,
                           top=0.95, bottom=0.06, left=0.08, right=0.97)

    # ── Panel 1: mid price + signal lines ───────────────────────────────────
    ax0 = fig.add_subplot(gs[0])
    ax0.plot(timestamps, mids, color=C_MID, lw=1.1, zorder=2, label="Mid price")
    if fair_line:
        ax0.plot(timestamps, fair_line, color=C_FAIR, lw=1.2, ls="--",
                 alpha=0.7, zorder=1, label="Fair value")

    legend_handles = [
        plt.Line2D([0],[0], color=C_MID, lw=1.5, label="Mid price"),
    ]
    if fair_line:
        legend_handles.append(
            plt.Line2D([0],[0], color=C_FAIR, lw=1.5, ls="--", label="Fair value"))

    for reason, sigs in reason_groups.items():
        bc, sc = REASON_COLORS.get(reason, (C_BUY, C_SELL))
        buys  = [s for s in sigs if s.side == "BUY"]
        sells = [s for s in sigs if s.side == "SELL"]
        # Draw vertical lines at each signal timestamp
        for s in buys:
            ax0.axvline(s.timestamp, color=bc, lw=0.5, alpha=0.25, zorder=1)
        for s in sells:
            ax0.axvline(s.timestamp, color=sc, lw=0.5, alpha=0.25, zorder=1)
        # Scatter at order price
        if buys:
            ax0.scatter([s.timestamp for s in buys], [s.price for s in buys],
                        color=bc, marker="^", s=30, zorder=5, alpha=0.8,
                        label=f"BUY ({reason})")
            legend_handles.append(
                plt.Line2D([0],[0], marker="^", color="w", markerfacecolor=bc,
                           markersize=8, label=f"BUY [{reason}]"))
        if sells:
            ax0.scatter([s.timestamp for s in sells], [s.price for s in sells],
                        color=sc, marker="v", s=30, zorder=5, alpha=0.8,
                        label=f"SELL ({reason})")
            legend_handles.append(
                plt.Line2D([0],[0], marker="v", color="w", markerfacecolor=sc,
                           markersize=8, label=f"SELL [{reason}]"))

    ax0.legend(handles=legend_handles, fontsize=8, framealpha=0.8,
               loc="upper left", ncol=2)
    style(ax0, "Mid price vs algo order prices")
    ax0.set_ylabel("Price", fontsize=8, color="#555")
    ax0.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x,_: f"{x:,.0f}"))

    # ── Panel 2: signal count per timestamp (buy/sell bar) ──────────────────
    ax1 = fig.add_subplot(gs[1])
    buy_ts  = [s.timestamp for s in signals if s.side == "BUY"]
    sell_ts = [s.timestamp for s in signals if s.side == "SELL"]
    buy_qty  = [s.qty for s in signals if s.side == "BUY"]
    sell_qty = [-s.qty for s in signals if s.side == "SELL"]

    if buy_ts:
        ax1.bar(buy_ts,  buy_qty,  color=C_BUY,  alpha=0.7, width=max(1, (max(timestamps)-min(timestamps))//300),
                label="Buy qty", zorder=2)
    if sell_ts:
        ax1.bar(sell_ts, sell_qty, color=C_SELL, alpha=0.7, width=max(1, (max(timestamps)-min(timestamps))//300),
                label="Sell qty", zorder=2)
    ax1.axhline(0, color="#aaa", lw=0.8)
    ax1.legend(fontsize=8, framealpha=0.8)
    style(ax1, "Order quantity at each timestamp  (positive = buy, negative = sell)")
    ax1.set_ylabel("Qty", fontsize=8, color="#555")

    # ── Panel 3 (pepper only): residual from trend ──────────────────────────
    if show_residual:
        ax2 = fig.add_subplot(gs[2])
        residuals = [m - f for m, f in zip(mids, fair_line)]
        ax2.plot(timestamps, residuals, color="#534AB7", lw=0.9, alpha=0.85)
        ax2.axhline(0,  color="#aaa", lw=0.8, ls=":")
        ax2.axhline( 6, color=C_SELL, lw=1.0, ls="--", alpha=0.7, label="Entry threshold +-6")
        ax2.axhline(-6, color=C_BUY,  lw=1.0, ls="--", alpha=0.7)
        # Mark residual-triggered signals
        for s in signals:
            if "resid" in s.reason:
                col = C_BUY if s.side == "BUY" else C_SELL
                mk  = "^" if s.side == "BUY" else "v"
                idx = next((i for i,t in enumerate(ticks) if t.timestamp==s.timestamp), None)
                if idx is not None:
                    ax2.scatter(s.timestamp, residuals[idx], color=col, marker=mk, s=40, zorder=5)
        ax2.legend(fontsize=8, framealpha=0.8)
        style(ax2, "Residual from trend  (mean-reversion signal)")
        ax2.set_ylabel("Residual (pts)", fontsize=8, color="#555")
        ax2.set_xlabel("Timestamp", fontsize=8, color="#555")
    else:
        ax1.set_xlabel("Timestamp", fontsize=8, color="#555")

    # Sync x-axis
    for ax in fig.get_axes():
        ax.set_xlim(min(timestamps), max(timestamps))

    plt.tight_layout(rect=[0, 0, 1, 0.97])

    if out:
        plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=BG)
        print(f"Saved -> {out}")
    else:
        plt.show()


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="IMC Signal Visualiser")
    parser.add_argument("--files",   nargs="+", required=True,
                        help="Price CSV files (semicolon-delimited)")
    parser.add_argument("--product", required=True,
                        help="Product name e.g. INTARIAN_PEPPER_ROOT")
    parser.add_argument("--day",     type=int, default=None,
                        help="Filter to a single day (-2, -1, 0).  Default = all.")
    parser.add_argument("--out",     default=None,
                        help="Output PNG path. If omitted, opens interactively.")
    args = parser.parse_args()

    missing = [f for f in args.files if not os.path.exists(f)]
    if missing:
        sys.exit(f"Files not found: {missing}")

    print(f"Loading {len(args.files)} file(s)...")
    ticks = load_ticks(args.files, args.product, args.day)
    print(f"  {len(ticks)} ticks loaded for {args.product}")

    print("Running signal engine...")
    signals = compute_signals(ticks, args.product)
    buys  = [s for s in signals if s.side == "BUY"]
    sells = [s for s in signals if s.side == "SELL"]
    print(f"  {len(buys)} buy signals, {len(sells)} sell signals")

    # Print a quick summary table to terminal
    print(f"\n{'─'*60}")
    print(f"{'REASON':<20} {'BUY':>6} {'SELL':>6}")
    print(f"{'─'*60}")
    for reason in sorted(set(s.reason for s in signals)):
        nb = sum(1 for s in signals if s.reason==reason and s.side=="BUY")
        ns = sum(1 for s in signals if s.reason==reason and s.side=="SELL")
        print(f"  {reason:<18} {nb:>6} {ns:>6}")
    print(f"{'─'*60}\n")

    out = args.out or f"{args.product}_signals.png"
    plot(ticks, signals, args.product, args.day, out)


if __name__ == "__main__":
    main()