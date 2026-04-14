"""
IMC Trading Log Visualiser
==========================
Usage:
    python visualise_log.py <path_to_log_file.log>

    e.g.  python visualise_log.py 96451.log

Produces a dashboard with:
  - Summary metrics (total PnL, per-product PnL, trade counts)
  - Emerald mid-price chart with buy/sell trade markers
  - Tomato mid-price chart with buy/sell trade markers
  - Cumulative PnL chart (Emerald + Tomato + combined)
  - Trade log table printed to terminal

Requirements:
    pip install matplotlib pandas
"""

import json
import sys
import os
from io import StringIO

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.ticker as mticker
from matplotlib.lines import Line2D
from matplotlib.patches import Patch


# ── Colour palette ────────────────────────────────────────────────────────────
BUY_COL   = "#1D9E75"   # teal-green
SELL_COL  = "#D85A30"   # coral
EM_COL    = "#185FA5"   # blue
TOM_COL   = "#854F0B"   # amber-brown
PNL_COL   = "#534AB7"   # purple
GRID_COL  = "#e8e8e8"
BG        = "#fafafa"
PANEL_BG  = "white"


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_log(path: str) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def parse_activities(log: dict) -> pd.DataFrame:
    raw = log.get("activitiesLog", "")
    if not raw.strip():
        return pd.DataFrame()
    df = pd.read_csv(StringIO(raw), sep=";")
    df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
    df["mid_price"] = pd.to_numeric(df["mid_price"], errors="coerce")
    df["profit_and_loss"] = pd.to_numeric(df["profit_and_loss"], errors="coerce")
    return df


def parse_trades(log: dict) -> pd.DataFrame:
    raw = log.get("tradeHistory", [])
    if not raw:
        return pd.DataFrame(columns=["timestamp","buyer","seller","symbol","price","quantity"])
    df = pd.DataFrame(raw)
    df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
    df["price"]     = pd.to_numeric(df["price"], errors="coerce")
    df["quantity"]  = pd.to_numeric(df["quantity"], errors="coerce")
    df["side"] = df.apply(
        lambda r: "BUY" if r["buyer"] == "SUBMISSION" else "SELL", axis=1
    )
    return df


def build_combined_pnl(acts: pd.DataFrame) -> pd.DataFrame:
    """Forward-fill each product's PnL onto a shared timestamp axis."""
    products = acts["product"].dropna().unique()
    all_ts = sorted(acts["timestamp"].dropna().unique())
    combined = pd.DataFrame({"timestamp": all_ts})
    for prod in products:
        sub = (
            acts[acts["product"] == prod][["timestamp", "profit_and_loss"]]
            .dropna()
            .drop_duplicates("timestamp")
            .sort_values("timestamp")
        )
        combined = combined.merge(sub.rename(columns={"profit_and_loss": prod}),
                                  on="timestamp", how="left")
        combined[prod] = combined[prod].ffill().fillna(0)
    combined["TOTAL"] = combined[[p for p in products if p in combined.columns]].sum(axis=1)
    return combined, list(products)


def errors_in_log(log: dict) -> int:
    logs = log.get("logs", [])
    return sum(1 for l in logs if "ERROR" in str(l.get("sandboxLog", "")))


# ── Plotting ──────────────────────────────────────────────────────────────────

def style_ax(ax, title=""):
    ax.set_facecolor(PANEL_BG)
    ax.grid(True, color=GRID_COL, linewidth=0.6, zorder=0)
    ax.spines[["top","right"]].set_visible(False)
    ax.spines[["left","bottom"]].set_color("#cccccc")
    ax.tick_params(colors="#555555", labelsize=9)
    if title:
        ax.set_title(title, fontsize=11, fontweight="normal", color="#333333", pad=8)


def plot_price_chart(ax, price_df: pd.DataFrame, trade_df: pd.DataFrame,
                     product: str, color: str):
    """Price line + trade scatter for one product."""
    ax.plot(price_df["timestamp"], price_df["mid_price"],
            color=color, linewidth=1.2, zorder=2, label="Mid price")

    if not trade_df.empty:
        prod_trades = trade_df[trade_df["symbol"] == product]
        buys  = prod_trades[prod_trades["side"] == "BUY"]
        sells = prod_trades[prod_trades["side"] == "SELL"]

        if not buys.empty:
            ax.scatter(buys["timestamp"], buys["price"],
                       color=BUY_COL, marker="^", s=55, zorder=5,
                       label=f"Buy ({len(buys)})")
        if not sells.empty:
            ax.scatter(sells["timestamp"], sells["price"],
                       color=SELL_COL, marker="v", s=55, zorder=5,
                       label=f"Sell ({len(sells)})")

    style_ax(ax, f"{product.capitalize()} — mid price")
    ax.set_ylabel("Price", fontsize=9, color="#555")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    ax.legend(fontsize=8, framealpha=0.7, loc="upper left")


def plot_pnl_chart(ax, pnl_df: pd.DataFrame, products: list):
    """Cumulative PnL lines — one per product + combined."""
    prod_colors = {
        "EMERALDS": EM_COL,
        "TOMATOES": TOM_COL,
    }
    for prod in products:
        if prod in pnl_df.columns:
            ax.plot(pnl_df["timestamp"], pnl_df[prod],
                    color=prod_colors.get(prod, "#888"), linewidth=1,
                    linestyle="--", alpha=0.7, label=prod.capitalize())

    total = pnl_df["TOTAL"]
    final = total.iloc[-1]
    fill_col = BUY_COL if final >= 0 else SELL_COL
    ax.plot(pnl_df["timestamp"], total,
            color=PNL_COL, linewidth=2, label=f"Combined  ({final:+.0f})", zorder=4)
    ax.fill_between(pnl_df["timestamp"], 0, total,
                    alpha=0.08, color=fill_col, zorder=1)
    ax.axhline(0, color="#aaa", linewidth=0.8, linestyle=":")

    style_ax(ax, "Cumulative PnL")
    ax.set_ylabel("PnL", fontsize=9, color="#555")
    ax.set_xlabel("Timestamp", fontsize=9, color="#555")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(
        lambda x, _: f"{x:+,.0f}"))
    ax.legend(fontsize=8, framealpha=0.7, loc="upper left")


def add_metrics_panel(fig, acts: pd.DataFrame, trades: pd.DataFrame,
                       err_count: int, log_path: str):
    """Text block at the very top with key numbers."""
    products = acts["product"].dropna().unique()
    pnl_per_prod = {}
    for prod in products:
        sub = acts[acts["product"] == prod]["profit_and_loss"].dropna()
        pnl_per_prod[prod] = sub.iloc[-1] if len(sub) else 0.0

    total_pnl = sum(pnl_per_prod.values())
    n_trades   = len(trades)

    lines = [f"File: {os.path.basename(log_path)}   |   "
             f"Errors: {err_count}   |   "
             f"Trades: {n_trades}   |   "
             f"Total PnL: {total_pnl:+.0f}"]
    for prod, pnl in pnl_per_prod.items():
        lines[0] += f"   |   {prod.capitalize()} PnL: {pnl:+.0f}"

    color = BUY_COL if total_pnl >= 0 else SELL_COL
    fig.text(0.5, 0.98, lines[0], ha="center", va="top",
             fontsize=9.5, color=color, fontweight="normal",
             bbox=dict(boxstyle="round,pad=0.4", facecolor="#f0f4ff",
                       edgecolor="#d0d8f0", linewidth=0.8))


def print_trade_table(trades: pd.DataFrame):
    if trades.empty:
        print("No trades found.")
        return
    print("\n" + "═"*72)
    print(f"{'TRADE LOG':^72}")
    print("═"*72)
    fmt = "{:<8} {:<10} {:<4} {:>8} {:>6}  {}"
    print(fmt.format("TIME", "PRODUCT", "SIDE", "PRICE", "QTY", "NOTE"))
    print("─"*72)
    for _, r in trades.sort_values("timestamp").iterrows():
        note = "▲ BUY " if r["side"] == "BUY" else "▼ SELL"
        print(fmt.format(
            int(r["timestamp"]),
            str(r["symbol"])[:10],
            r["side"],
            f"{r['price']:,.1f}",
            int(r["quantity"]),
            note
        ))
    print("─"*72)
    buys  = trades[trades["side"]=="BUY"]
    sells = trades[trades["side"]=="SELL"]
    print(f"Total: {len(trades)} trades  |  "
          f"Buys: {len(buys)}  |  Sells: {len(sells)}")
    print("═"*72 + "\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python visualise_log.py <log_file.log>")
        sys.exit(1)

    log_path = sys.argv[1]
    if not os.path.exists(log_path):
        print(f"File not found: {log_path}")
        sys.exit(1)

    print(f"Loading {log_path}...")
    log   = load_log(log_path)
    acts  = parse_activities(log)
    trades = parse_trades(log)
    errs  = errors_in_log(log)

    if acts.empty:
        print("No activity data found in log file.")
        sys.exit(1)

    pnl_df, products = build_combined_pnl(acts)

    print_trade_table(trades)

    # ── Build figure layout ───────────────────────────────────────────────────
    n_price_charts = len(products)
    n_rows = n_price_charts + 1   # price charts + PnL chart

    fig = plt.figure(figsize=(13, 4 + n_rows * 3.2), facecolor=BG)
    fig.subplots_adjust(top=0.93, bottom=0.06, left=0.07, right=0.97,
                        hspace=0.45)

    gs = gridspec.GridSpec(n_rows, 1, figure=fig)
    axes = [fig.add_subplot(gs[i]) for i in range(n_rows)]

    add_metrics_panel(fig, acts, trades, errs, log_path)

    prod_colors = {"EMERALDS": EM_COL, "TOMATOES": TOM_COL}

    for i, prod in enumerate(products):
        prod_df = acts[acts["product"] == prod].dropna(subset=["mid_price"])
        color   = prod_colors.get(prod, "#666")
        plot_price_chart(axes[i], prod_df, trades, prod, color)

    plot_pnl_chart(axes[-1], pnl_df, products)

    # Sync x-axis across all panels
    all_ts = acts["timestamp"].dropna()
    x_min, x_max = all_ts.min(), all_ts.max()
    margin = (x_max - x_min) * 0.02
    for ax in axes:
        ax.set_xlim(x_min - margin, x_max + margin)
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(
            lambda x, _: f"{int(x):,}"))

    plt.suptitle("IMC Trading Dashboard", fontsize=14, fontweight="normal",
                 color="#222", y=0.995)

    base_dir = "logs_visualised"
    base_name = os.path.splitext(os.path.basename(log_path))[0]
    out_path = os.path.join(os.getcwd(), f"{base_dir}/{base_name}_dashboard.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=BG)
    print(f"Dashboard saved → {out_path}")
    plt.show()


if __name__ == "__main__":
    main()