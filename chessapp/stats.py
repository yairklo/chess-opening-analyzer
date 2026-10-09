"""Opening tree, statistics, toxic openings and problem positions.

Everything except loading is recomputed for the current filter (colour / speed), so thresholds such as
MIN_GROUP_GAMES always apply to the games actually shown.
"""
from collections import Counter, defaultdict

import chess
import pandas as pd

from . import config as C
from .analyze import db, fen_key

ERR_COLS = ["fen_before", "played", "played_san", "best", "eval_before", "eval_after", "win_before", "win_after", "drop"]


def load_results(user: str = C.USER, threshold: float = C.ERROR_WIN_DROP):
    """(games, errors) of one player: one row per analysed game, one row per error (win% drop >= threshold)
    in the analysed plies. `errors` is empty until the Stockfish analysis has run for that player."""
    con = db()
    user = user.lower()
    games = pd.read_sql("select * from game_results where user=?", con, params=(user,))
    try:
        errors = pd.read_sql("select * from errors where user=?", con, params=(user,))
    except Exception:
        errors = pd.DataFrame(columns=["id", "ply", "fen_before", "played", "played_san", "best", "eval_before",
                                       "eval_after", "win_before", "win_after", "drop"])
    errors = errors[(errors["drop"] >= threshold) & (errors.played != errors.best)]
    errors = errors.drop(columns="user", errors="ignore").merge(games[["id", "color"]], on="id")
    errors["key"] = errors.fen_before.map(lambda f: " ".join(f.split()[:4]))
    return games, errors


# ---------------------------------------------------------------- opening tree
def build_tree(games: pd.DataFrame) -> dict:
    """Per colour: (kept prefixes, prefix counts). A prefix (<= LINE_MAX_PLIES plies) is a node when
    >= MIN_GROUP_GAMES games share it; a node with a single child is dropped unless it holds at least
    MIN_GROUP_GAMES games of its own beyond that child (otherwise it would only repeat the child; this applies
    to first moves too, so 1.e4 disappears when every 1.e4 game continued 1...e5)."""
    tree = {}
    for color, sub in games.groupby("color"):
        cnt = Counter()
        for line in sub.line:
            s = line.split()
            for k in range(1, len(s) + 1):
                cnt[tuple(s[:k])] += 1
        cand = {p for p, n in cnt.items() if n >= C.MIN_GROUP_GAMES}
        children = defaultdict(list)
        for p in cand:
            if len(p) > 1:
                children[p[:-1]].append(p)
        keep = {p for p in cand
                if len(children[p]) != 1 or cnt[p] - cnt[children[p][0]] >= C.MIN_GROUP_GAMES}
        tree[color] = (keep, cnt)
    return tree


def prepare(games: pd.DataFrame, errors: pd.DataFrame):
    """Assign every game to its deepest tree node and pick its first error *after* that node's moves:
    an "error" inside a line shared by many games is a deliberate repertoire choice (e.g. a gambit).
    Returns (games with first-error columns, errors after the group line, tree)."""
    tree = build_tree(games)
    g = games.copy()
    groups = []
    for color, line in zip(g.color, g.line):
        keep = tree[color][0]
        s = tuple(line.split())
        groups.append(max((s[:k] for k in range(1, len(s) + 1) if s[:k] in keep), key=len, default=()))
    g["group"] = [" ".join(p) for p in groups]
    g["group_plies"] = [len(p) for p in groups]
    e = errors[errors.id.isin(g.id)].merge(g[["id", "group_plies"]], on="id")
    rel = e[e.ply > e.group_plies].drop(columns="group_plies")
    first = rel.sort_values("ply").drop_duplicates("id").set_index("id")
    g = g.join(first[ERR_COLS + ["ply"]].rename(columns={"ply": "first_error_ply"}), on="id")
    g["first_error_move"] = (g.first_error_ply + 1) // 2
    g["early_error"] = g.first_error_move <= C.EARLY_ERROR_MOVE
    return g, rel, tree


def node_name(openings: pd.Series) -> tuple:
    """(name, exact): the Lichess name when most games agree on it, else the family (part before ':'),
    else the two main families."""
    top = openings.value_counts(normalize=True)
    if top.iat[0] >= 0.6:
        return top.index[0], True
    fam = openings.str.split(":").str[0].value_counts(normalize=True)
    if fam.iat[0] >= 0.6:
        return fam.index[0], False
    return " / ".join(fam.index[:2]) + (" / …" if len(fam) > 2 else ""), False


def opening_table(g: pd.DataFrame, errors: pd.DataFrame, tree: dict) -> pd.DataFrame:
    """One row per tree node (sums include all deeper nodes), in tree order (children by games)."""
    rows = []
    for color, sub in g.groupby("color"):
        keep, _ = tree[color]
        base = sub.score.mean()
        seqs = sub.line.str.split()
        ce = errors[errors.id.isin(sub.id)]
        for p in keep:
            s = sub[seqs.map(lambda x: tuple(x[:len(p)]) == p)]
            n = len(s)
            # errors after this node's own moves; first one per game
            fe = ce[ce.id.isin(s.id) & (ce.ply > len(p))].sort_values("ply").drop_duplicates("id")
            early = ((fe.ply + 1) // 2 <= C.EARLY_ERROR_MOVE).sum() / n
            top_label, top_n = "", 0
            if len(fe):
                vc = (fe.key + "|" + fe.played_san).value_counts()
                top_n = int(vc.iat[0])
                r = fe[(fe.key + "|" + fe.played_san) == vc.index[0]].iloc[0]
                top_label = move_label(int(r.ply), r.played_san)
            score = s.score.mean()
            name, exact = node_name(s.opening)
            parent = next((p[:k] for k in range(len(p) - 1, 0, -1) if p[:k] in keep), None)
            rows.append(dict(
                color=color, group=" ".join(p), plies=len(p), parent=" ".join(parent) if parent else "",
                line=pretty_line(" ".join(p)), games=n, base=base,
                win=(s.result == "win").mean(), draw=(s.result == "draw").mean(), loss=(s.result == "loss").mean(),
                score=score, cost=max(0.0, n * (base - score)), avg_first_error_move=((fe.ply + 1) // 2).mean(),
                early_error_share=early, opening=name, eco=s.eco.mode().iat[0] if exact else "",
                top_error=top_label, top_error_count=top_n, top_error_share=top_n / n,
                toxic=bool(score < base - C.TOXIC_MARGIN and early >= C.EARLY_ERROR_SHARE
                           and top_n >= C.MIN_PROBLEM_GAMES)))
    t = pd.DataFrame(rows)
    if t.empty:
        return t
    t["key"] = t.color + "|" + t.group
    # depth-first order, children sorted by number of games
    kids = defaultdict(list)
    for r in t.itertuples():
        kids[(r.color, r.parent)].append(r)
    order, depth = {}, {}

    def walk(color, parent, d):
        for r in sorted(kids[(color, parent)], key=lambda r: -r.games):
            order[r.key], depth[r.key] = len(order), d
            walk(color, r.group, d + 1)

    for color in ("white", "black"):
        walk(color, "", 0)
    t["order"], t["depth"] = t.key.map(order), t.key.map(depth)
    return t.sort_values("order").reset_index(drop=True)


# ---------------------------------------------------------------- labels
def pretty_line(line: str) -> str:
    out, toks = [], line.split()
    for i, t in enumerate(toks):
        out.append(f"{i // 2 + 1}.{t}" if i % 2 == 0 else (t if out else f"{i // 2 + 1}...{t}"))
    return " ".join(out) or "(start)"


def move_label(ply: int, san: str) -> str:
    """'9...Qa5' style label for a 1-based ply."""
    return f"{(ply + 1) // 2}{'.' if ply % 2 else '...'}{san}"


def san_of(fen: str, uci: str):
    if not uci:
        return None
    b = chess.Board(fen)
    try:
        return b.san(chess.Move.from_uci(uci))
    except ValueError:
        return uci


def overall(df):
    return dict(games=len(df), win=(df.result == "win").mean(), draw=(df.result == "draw").mean(),
                loss=(df.result == "loss").mean(), score=df.score.mean(),
                avg_first_error_move=df.first_error_move.mean(),
                games_with_error=int(df.first_error_ply.notna().sum()))


# ---------------------------------------------------------------- problem positions
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
    """How often the mistake was repeated each time the position was reached, whether it was fixed,
    and which move the user usually plays there.
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
    moves = o.san.value_counts()
    return dict(reached=n, mistakes=m, rate=m / n if n else 0.0, recent_rate=float(recent.mean()) if n else 0.0,
                since_last=since, status=status, moves=moves.to_dict(),
                usual=moves.index[0] if n else played, usual_n=int(moves.iat[0]) if n else 0,
                last_mistake=pd.to_datetime(o.created.iat[last_idx], unit="ms").strftime("%Y-%m-%d") if last_idx >= 0 else "")


SORTS = {"count": lambda r: (-r["count"], -r["total_drop"]),
         "avg_drop": lambda r: (-r["avg_drop"], -r["count"]),
         "total_drop": lambda r: (-r["total_drop"], -r["count"]),
         "default": lambda r: (r["count"] < C.MIN_PROBLEM_GAMES, -r["total_drop"])}  # recurring positions first


def problem_positions(g: pd.DataFrame, rel: pd.DataFrame, occ: pd.DataFrame, color: str,
                      min_games: int = 1, sort="default", base=None):
    """Errors grouped by (position, move played) for one colour. `rel` = errors after each game's group line.
    A move played in >= GAMBIT_MIN_GAMES games that scores above the colour's average is a working choice, not a problem."""
    sub = g[g.color == color]
    e = rel[(rel.color == color) & rel.id.isin(sub.id)]
    if e.empty:
        return []
    avg = sub.score.mean() if base is None else base
    info = sub.set_index("id")
    out = []
    for (key, played), s in e.groupby(["key", "played_san"]):
        ids = list(dict.fromkeys(s.id))
        if len(ids) < min_games:
            continue
        score = float(info.score.reindex(ids).mean())
        if len(ids) >= C.GAMBIT_MIN_GAMES and score > avg:
            continue
        r = s.iloc[0]
        best_uci = s.best.dropna().mode().iat[0] if s.best.notna().any() else None
        # what the opponents actually answered, and how those games ended
        replies = defaultdict(list)
        for i in ids:
            mv = info.moves[i].split()
            if len(mv) > r.ply:
                replies[mv[int(r.ply)]].append(info.score[i])
        replies = sorted(({"san": k, "n": len(v), "score": sum(v) / len(v)} for k, v in replies.items()),
                         key=lambda x: -x["n"])
        out.append(dict(key=key, fen=r.fen_before, color=color, count=len(ids), total_drop=float(s["drop"].sum()),
                        avg_drop=float(s["drop"].mean()), win_before=float(s.win_before.mean()),
                        win_after=float(s.win_after.mean()), played=played, played_uci=r.played,
                        best_uci=best_uci, best_san=san_of(r.fen_before, best_uci), ply=int(r.ply),
                        pre_moves=info.moves[r.id].split()[: int(r.ply) - 1],
                        opening=info.opening.reindex(ids).mode().iat[0],
                        score=score, games=ids, share=len(ids) / len(sub), replies=replies,
                        cost=len(ids) * (avg - score), avg=avg, **learning(occ, color, key, played)))
    out.sort(key=SORTS[sort])
    return out
