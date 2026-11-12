"""Build data/spx.csv and data/stoxx50e.csv from files downloaded by hand.

Used when fetch_history.py cannot reach Yahoo. Sources:

- Investing.com "Historical Data" CSV exports (one or more files per index;
  each export is capped at 5,000 rows, so a long history comes in pieces).
- For the Euro Stoxx 50 before the first Investing.com date: the index
  provider's own file of daily closes (stoxx.com, hbrbcpe.txt, column SX5E).

Where two sources overlap, the script prints how far apart they are, so the
splice can be checked. Usage:

    python import_history.py <folder with the downloaded files>
"""
import sys
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
START = "2000-01-01"


def read_investing(path: Path) -> pd.Series:
    """Closes from one Investing.com export (dates as MM/DD/YYYY, prices like "3,096.60")."""
    frame = pd.read_csv(path, thousands=",")
    dates = pd.to_datetime(frame["Date"], format="%m/%d/%Y")
    return pd.Series(frame["Price"].astype(float).to_numpy(), index=dates).sort_index()


def read_investing_all(folder: Path, prefix: str) -> pd.Series:
    """All exports of one index joined into one series, duplicates dropped."""
    files = sorted(folder.glob(f"{prefix} Historical Data*.csv"))
    if not files:
        raise FileNotFoundError(f"no '{prefix} Historical Data*.csv' in {folder}")
    joined = pd.concat([read_investing(f) for f in files])
    return joined[~joined.index.duplicated(keep="last")].sort_index()


def read_stoxx(path: Path) -> pd.Series:
    """SX5E closes from the STOXX file: ';' separated, dates as DD.MM.YYYY, SX5E in the third column."""
    rows = {}
    for line in path.read_text().splitlines():
        parts = [p.strip() for p in line.split(";")]
        if len(parts) > 2 and len(parts[0]) == 10 and parts[0][2] == ".":
            rows[pd.to_datetime(parts[0], format="%d.%m.%Y")] = float(parts[2])
    return pd.Series(rows).sort_index()


def splice(old: pd.Series, new: pd.Series) -> pd.Series:
    """`new` where it exists, `old` before its first date. Prints the overlap check."""
    both = pd.concat([old, new], axis=1, join="inner")
    gap = (both.iloc[:, 0] / both.iloc[:, 1] - 1).abs()
    print(f"  overlap: {len(both)} days, median gap {gap.median():.4%}, max gap {gap.max():.4%}")
    return pd.concat([old[old.index < new.index[0]], new])


def save(close: pd.Series, filename: str) -> None:
    close = close[close.index >= START].round(2)
    close.index = close.index.date
    close.index.name = "date"
    close.name = "close"
    DATA_DIR.mkdir(exist_ok=True)
    close.to_csv(DATA_DIR / filename)
    print(f"  {len(close)} closes, {close.index[0]} to {close.index[-1]} -> data/{filename}")


def main(folder: Path) -> None:
    print("S&P 500")
    save(read_investing_all(folder, "S&P 500"), "spx.csv")
    print("Euro Stoxx 50")
    sx5e = read_investing_all(folder, "Euro Stoxx 50")
    stoxx_file = folder / "hbrbcpe.txt"
    if stoxx_file.exists():
        sx5e = splice(read_stoxx(stoxx_file), sx5e)
    save(sx5e, "stoxx50e.csv")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
