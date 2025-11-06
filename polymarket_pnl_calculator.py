from __future__ import annotations
import dataclasses as dc
from dataclasses import dataclass
from typing import Optional, Dict, Any
import argparse
import pandas as pd
import math
import os
import re
from datetime import datetime

# Optional OCR imports (used only if user provides a screenshot and has Tesseract installed)
try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except Exception:
    OCR_AVAILABLE = False

OUTPUT_DIR = "."  # current folder by default

@dataclass
class FeeConfig:
    profit_fee_pct: float = 0.02     # 2% on net profit if you win
    trading_fee_pct: float = 0.0     # 0% trading fee by default (can be set if applicable)
    taker_fee_pct: float = 0.0001    # 0.01% taker fee; set to 0 if not applicable
    gas_cost: float = 0.0            # flat USDC gas cost

@dataclass
class InputParams:
    market_title: str
    side: str               # 'yes' or 'no'
    stake_usdc: float
    entry_price: float      # price per share paid (0..1)
    settlement_per_share: float = 1.0
    fee_cfg: FeeConfig = dc.field(default_factory=FeeConfig)

def _clean_text(txt: str) -> str:
    return re.sub(r"\\s+", " ", txt).strip()

def try_ocr_extract(path: str) -> Dict[str, Any]:
    """
    Try extracting market title and YES/NO prices from a Polymarket screenshot via OCR.
    """
    if not OCR_AVAILABLE:
        return {"ocr_available": False, "warning": "OCR not available. Install Tesseract and pillow/pytesseract to use screenshot parsing."}

    try:
        img = Image.open(path)
        raw = pytesseract.image_to_string(img)
        text = _clean_text(raw)
    except Exception as e:
        return {"ocr_available": False, "warning": f"OCR failed to read image: {e}"}

    yes_price = None
    no_price = None
    title_guess = None

    lines = [l.strip() for l in re.split(r"[\\r\\n]+", raw) if l.strip()]
    if lines:
        cand = sorted(lines, key=lambda s: len(s), reverse=True)
        for c in cand:
            if not re.search(r"\\$|¢|\\d{1,2}\\.\\d{1,3}", c):
                title_guess = _clean_text(c)
                break

    m_yes = re.search(r"[Yy]es[^$0-9¢]*((?:\\$)?[0]?\\.[0-9]{1,3}|[0-9]{1,2}¢)", text)
    m_no  = re.search(r"[Nn]o[^$0-9¢]*((?:\\$)?[0]?\\.[0-9]{1,3}|[0-9]{1,2}¢)", text)

    def norm_price(s: Optional[str]) -> Optional[float]:
        if not s:
            return None
        s = s.replace("$","").strip().lower()
        if s.endswith("¢"):
            try:
                v = float(s[:-1])
                return v/100.0
            except:
                return None
        try:
            return float(s)
        except:
            return None

    if m_yes:
        yes_price = norm_price(m_yes.group(1))
    if m_no:
        no_price = norm_price(m_no.group(1))

    return {
        "ocr_available": True,
        "title": title_guess,
        "yes_price": yes_price,
        "no_price": no_price,
        "raw_text": text
    }

def calc_pnl(params: InputParams) -> Dict[str, Any]:
    side = params.side.strip().lower()
    if side not in ("yes", "no"):
        raise ValueError("side must be 'yes' or 'no'")

    stake = float(params.stake_usdc)
    price = float(params.entry_price)
    settlement = float(params.settlement_per_share)
    fee = params.fee_cfg

    if not (0 < price < settlement):
        raise ValueError("entry_price must be between 0 and 1.0 for binary markets")

    shares = stake / price

    trading_fee = stake * float(fee.trading_fee_pct)
    taker_fee = stake * float(fee.taker_fee_pct)
    gas_cost = float(fee.gas_cost)

    gross_payout_if_win = shares * settlement
    gross_profit_if_win = gross_payout_if_win - stake
    profit_fee = max(0.0, gross_profit_if_win) * float(fee.profit_fee_pct)
    net_profit_if_win = gross_profit_if_win - profit_fee - trading_fee - taker_fee - gas_cost
    net_payout_if_win = stake + net_profit_if_win

    net_loss_if_lose = stake + trading_fee + taker_fee + gas_cost
    net_payout_if_lose = 0.0

    rr_win_pct = (net_profit_if_win / stake) * 100.0
    rr_lose_pct = -(net_loss_if_lose / stake) * 100.0

    return {
        "market_title": params.market_title,
        "side": side.upper(),
        "stake_usdc": round(stake, 2),
        "entry_price": round(price, 4),
        "shares": round(shares, 6),
        "settlement_per_share": settlement,
        "fees": {
            "profit_fee_pct": fee.profit_fee_pct,
            "trading_fee_pct": fee.trading_fee_pct,
            "taker_fee_pct": fee.taker_fee_pct,
            "gas_cost": fee.gas_cost
        },
        "win_case": {
            "gross_payout": round(gross_payout_if_win, 4),
            "gross_profit": round(gross_profit_if_win, 4),
            "profit_fee": round(profit_fee, 4),
            "entry_trading_fee": round(trading_fee, 4),
            "entry_taker_fee": round(taker_fee, 4),
            "gas_cost": round(gas_cost, 4),
            "net_profit": round(net_profit_if_win, 4),
            "net_payout": round(net_payout_if_win, 4),
            "return_pct": round(rr_win_pct, 3)
        },
        "lose_case": {
            "net_loss": round(net_loss_if_lose, 4),
            "net_payout": round(net_payout_if_lose, 4),
            "return_pct": round(-rr_lose_pct, 3)
        }
    }

def make_report(result: Dict[str, Any], output_dir: str = OUTPUT_DIR) -> Dict[str, str]:
    import pandas as pd
    rows = [{
        "Market": result["market_title"],
        "Side": result["side"],
        "Stake (USDC)": result["stake_usdc"],
        "Entry Price": result["entry_price"],
        "Shares": result["shares"],
        "Settlement/Share": result["settlement_per_share"],
        "Profit Fee % (if win)": result["fees"]["profit_fee_pct"],
        "Trading Fee %": result["fees"]["trading_fee_pct"],
        "Taker Fee %": result["fees"]["taker_fee_pct"],
        "Gas (USDC)": result["fees"]["gas_cost"],
        "Win: Gross Payout": result["win_case"]["gross_payout"],
        "Win: Gross Profit": result["win_case"]["gross_profit"],
        "Win: Profit Fee": result["win_case"]["profit_fee"],
        "Win: Entry Trading Fee": result["win_case"]["entry_trading_fee"],
        "Win: Entry Taker Fee": result["win_case"]["entry_taker_fee"],
        "Win: Gas": result["win_case"]["gas_cost"],
        "Win: Net Profit": result["win_case"]["net_profit"],
        "Win: Net Payout": result["win_case"]["net_payout"],
        "Win: Return %": result["win_case"]["return_pct"],
        "Lose: Net Loss": result["lose_case"]["net_loss"],
        "Lose: Net Payout": result["lose_case"]["net_payout"],
        "Lose: Return %": -result["lose_case"]["return_pct"],
    }]
    df = pd.DataFrame(rows)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    base = f"polymarket_pnl_report_{ts}"
    csv_path = os.path.join(output_dir, f"{base}.csv")
    xlsx_path = os.path.join(output_dir, f"{base}.xlsx")
    df.to_csv(csv_path, index=False)
    with pd.ExcelWriter(xlsx_path, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="PnL")
        wb = writer.book
        ws = writer.sheets["PnL"]
        for i, width in enumerate([28,8,12,10,12,15,15,12,12,10,14,14,14,18,16,10,14,14,12,14,14,12]):
            ws.set_column(i, i, width)
    return {"csv_path": csv_path, "xlsx_path": xlsx_path}

def run_calc_cli(args: argparse.Namespace) -> Dict[str, str]:
    title = args.title or "Polymarket Market"
    side = args.side
    stake = float(args.stake)
    fee_cfg = FeeConfig(
        profit_fee_pct=float(args.profit_fee_pct),
        trading_fee_pct=float(args.trading_fee_pct),
        taker_fee_pct=float(args.taker_fee_pct),
        gas_cost=float(args.gas)
    )

    entry_price = None
    if args.screenshot:
        ocr = try_ocr_extract(args.screenshot)
        if ocr.get("ocr_available"):
            if not title and ocr.get("title"):
                title = ocr["title"]
            if side.lower() == "yes" and ocr.get("yes_price") is not None:
                entry_price = ocr["yes_price"]
            elif side.lower() == "no" and ocr.get("no_price") is not None:
                entry_price = ocr["no_price"]

    if entry_price is None:
        if args.entry is None:
            raise SystemExit("No entry price found. Provide --entry or make sure OCR extracted it.")
        entry_price = float(args.entry)

    params = InputParams(
        market_title=title,
        side=side,
        stake_usdc=stake,
        entry_price=entry_price,
        settlement_per_share=1.0,
        fee_cfg=fee_cfg
    )
    res = calc_pnl(params)
    report_paths = make_report(res, output_dir=args.output_dir)
    print("CSV:", report_paths["csv_path"])
    print("XLSX:", report_paths["xlsx_path"])
    return report_paths

def build_arg_parser():
    p = argparse.ArgumentParser(description="Polymarket PnL Calculator (with optional OCR).")
    p.add_argument("--title", type=str, default="", help="Market title (optional; can be inferred by OCR).")
    p.add_argument("--stake", type=float, required=True, help="Stake size in USDC (amount spent).")
    p.add_argument("--side", type=str, required=True, choices=["yes","no"], help="Side you bought.")
    p.add_argument("--entry", type=float, help="Entry price (0..1).")
    p.add_argument("--screenshot", type=str, help="Optional path to a Polymarket screenshot. Requires Tesseract installed.")
    p.add_argument("--profit_fee_pct", type=float, default=0.02, help="Fee on net *profit* if you win (e.g., 0.02 for 2%).")
    p.add_argument("--trading_fee_pct", type=float, default=0.0, help="Trading fee on notional (apply if relevant; default 0).")
    p.add_argument("--taker_fee_pct", type=float, default=0.0001, help="Taker fee on notional (e.g., 0.0001=0.01%). Set 0 if N/A.")
    p.add_argument("--gas", type=float, default=0.0, help="Flat gas/network cost in USDC.")
    p.add_argument("--output_dir", type=str, default=".", help="Where to write CSV/XLSX reports.")
    return p

def main():
    parser = build_arg_parser()
    args = parser.parse_args()
    run_calc_cli(args)

if __name__ == "__main__":
    main()
