"""Opening grouping, statistics, toxic openings and problem positions."""
from collections import Counter

import chess
import pandas as pd

from . import config as C
from .analyze import db, fen_key
from .explorer import lookup


def load_results() -> pd.DataFrame:
    df = pd.read_sql("select * from game_results", db())
    df["first_error_move"] = (df["first_error_ply"] + 1) // 2   # own move number
    df = assign_groups(df)
    # An "error" inside the group's own shared line is a deliberate repertoire choice (e.g. a gambit),
    # so it does not count towards the early-error test used for toxic openings.
    df["early_error"] = (df["first_error_move"] <= C.EARLY_ERROR_MOVE) & (df["first_error_ply"] > df["group_plies"])
    return df


def assign_groups(df: pd.DataFrame) -> pd.DataFrame:
    """Group by move sequence up to the divergence point: the deepest prefix (<= LINE_MAX_PLIES)
    still shared by >= MIN_GROUP_GAMES games of the same colour."""
    df = df.copy()
    df["group"] = ""
    df["group_plies"] = 0
    for color, sub in df.groupby("color"):
        seqs = {i: l.split() for i, l in sub["line"].items()}
        cnt = Counter()
        for s in seqs.values():
            for k in range(1, len(s) + 1):
                cnt[tuple(s[:k])] += 1
        for i, s in seqs.items():
            best = 0
            for k in range(1, len(s) + 1):
                if cnt[tuple(s[:k])] >= C.MIN_GROUP_GAMES:
                    best = k
                else:
                    break
            df.loc[i, "group"] = " ".join(s[:best])
            df.loc[i, "group_plies"] = best
    return df


def pretty_line(line: str) -> str:
    out, toks = [], line.split()
    for i, t in enumerate(toks):
        out.append(f"{i // 2 + 1}.{t}" if i % 2 == 0 else (t if out else f"{i // 2 + 1}...{t}"))
    return " ".join(out) or "(start)"


def overall(df):
    return dict(games=len(df), win=(df.result == "win").mean(), draw=(df.result == "draw").mean(),
                loss=(df.result == "loss").mean(), score=df.score.mean(),
                avg_first_error_move=df.first_error_move.mean(),
                games_with_error=int(df.first_error_ply.notna().sum()))


def opening_table(df: pd.DataFrame, base_score: float = None) -> pd.DataFrame:
    """One row per (color, group) with >= MIN_GROUP_GAMES games."""
    if df.empty:
        return pd.DataFrame()
    base = df.score.mean() if base_score is None else base_score
    rows = []
    for (color, grp), s in df.groupby(["color", "group"]):
        n = len(s)
        if n < C.MIN_GROUP_GAMES or not grp:
            continue
        early_share = s.early_error.mean()
        score = s.score.mean()
        top_err = top_error(s)
        rows.append(dict(
            color=color, line=pretty_line(grp), group=grp, games=n,
            win=(s.result == "win").mean(), draw=(s.result == "draw").mean(), loss=(s.result == "loss").mean(),
            score=score, avg_first_error_move=s.first_error_move.mean(), early_error_share=early_share,
            eco=s.eco.mode().iat[0], opening=s.opening.mode().iat[0],
            top_error=top_err[0], top_error_share=top_err[1],
            toxic=bool(score < base - C.TOXIC_MARGIN and early_share >= C.EARLY_ERROR_SHARE)))
    return pd.DataFrame(rows).sort_values(["color", "score"]).reset_index(drop=True)


def top_error(s: pd.DataFrame):
    """Most common first error in a set of games: (label, share of all games in the set)."""
    e = s[s.first_error_ply.notna() & (s.first_error_ply > s.group_plies)]  # ignore the line's own (gambit) moves
    if e.empty:
        return "", 0.0
    keys = e.fen_before.map(lambda f: " ".join(f.split()[:4])) + "|" + e.played_san
    k, c = keys.value_counts().index[0], keys.value_counts().iat[0]
    ply = int(e.first_error_ply[keys == k].iat[0])
    mv = e.played_san[keys == k].iat[0]
    return f"{(ply + 1) // 2}{'.' if ply % 2 else '...'}{mv}", c / len(s)


def occurrences(df: pd.DataFrame) -> pd.DataFrame:
    """Every position in which the user was to move (within the analysed plies) and the move played."""
    rows = []
    for g in df.itertuples():
        b = chess.Board()
        me = chess.WHITE if g.color == "white" else chess.BLACK
        for san in g.moves.split()[: C.ANALYZE_PLIES]:
            if b.turn == me:
                rows.append((g.id, g.created, g.color, fen_key(b), san))
            try:
                b.push_san(san)
            except ValueError:
                break
    return pd.DataFrame(rows, columns=["id", "created", "color", "key", "san"])


def learning(occ: pd.DataFrame, color: str, key: str, played: str) -> dict:
    """How often the mistake was repeated each time the position was reached, and whether it was fixed.
    status: few (not enough visits) / learned / repeating (last visit was the mistake) / improving."""
    o = occ[(occ.color == color) & (occ.key == key)].sort_values("created")
    n = len(o)
    mist = (o.san == played).to_numpy()
    m = int(mist.sum())
    last_idx = max((i for i, x in enumerate(mist) if x), default=-1)
    since = n - 1 - last_idx
    recent = mist[-C.LEARN_RECENT:]
    if n < C.LEARN_MIN_REACHED:
        status = "few"
    elif since >= C.LEARN_FIXED_AFTER:
        status = "learned"
    elif since == 0:
        status = "repeating"
    else:
        status = "improving"
    return dict(reached=n, mistakes=m, rate=m / n if n else 0.0, recent_rate=float(recent.mean()) if n else 0.0,
                since_last=since, status=status,
                last_mistake=pd.to_datetime(o.created.iat[last_idx], unit="ms").strftime("%Y-%m-%d") if last_idx >= 0 else "")


def san_of(fen: str, uci: str):
    if not uci:
        return None
    b = chess.Board(fen)
    try:
        return b.san(chess.Move.from_uci(uci))
    except ValueError:
        return uci


SORTS = {"count": lambda r: (-r["count"], -r["total_drop"]),
         "avg_drop": lambda r: (-r["avg_drop"], -r["count"]),
         "total_drop": lambda r: (-r["total_drop"], -r["count"]),
         "default": lambda r: (r["count"] < 2, -r["total_drop"])}  # recurring positions first


def problem_positions(df: pd.DataFrame, color: str, top: int = C.TOP_POSITIONS, with_explorer=True, sort="default", base=None, occ=None):
    """Positions where the first error happens most costly (total cp lost), per colour."""
    e = df[(df.color == color) & df.first_error_ply.notna()].copy()
    if e.empty:
        return []
    e["key"] = e.fen_before.map(lambda f: " ".join(f.split()[:4]))
    out = []
    if occ is None:
        occ = occurrences(df)
    n_color = int((df.color == color).sum())
    avg = df[df.color == color].score.mean() if base is None else base
    for (key, played), s in e.groupby(["key", "played_san"]):
        # a deliberate move (e.g. a gambit) that scores above average over enough games is not a problem
        if len(s) >= C.GAMBIT_MIN_GAMES and s.score.mean() > avg:
            continue
        best_uci = s.best.dropna().mode().iat[0] if s.best.notna().any() else None
        fen = s.fen_before.iat[0]
        out.append(dict(key=key, fen=fen, count=len(s), total_drop=float(s["drop"].sum()),
                        avg_drop=float(s["drop"].mean()), played=played,
                        played_uci=s.played.iat[0],
                        best_uci=best_uci, best_san=san_of(fen, best_uci),
                        ply=int(s.first_error_ply.iat[0]),
                        line=pretty_line(" ".join(s.moves.iat[0].split()[: int(s.first_error_ply.iat[0]) - 1])),
                        score=float(s.score.mean()), games=list(s.id),
                        share=len(s) / n_color, **learning(occ, color, key, played)))
    out.sort(key=SORTS[sort])
    out = out[:top]
    if with_explorer:
        rating = int(df[df.color == color].rating.median())
        for r in out:
            r["explorer"] = lookup(r["fen"], rating)
    return out
