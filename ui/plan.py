"""What to fix: the picks behind the home page and the helpers shared with the repertoire screen."""
import re

from chessapp import config as C

from .common import CONF, en, esc, move_label, pct
from .ctx import ctx
from .data import by_cost, level_view, recurring, tr_key


def focus_openings(n):
    """Openings with the largest cost, skipping any node whose ancestor or descendant was already picked
    (tree rows include their children, so overlapping picks would count the same games twice)."""
    tbl = ctx.tbl
    picked = []
    if tbl.empty:
        return tbl
    for r in tbl[tbl.cost > 0].sort_values("cost", ascending=False).itertuples():
        if all(r.color != q.color or not (r.group.startswith(q.group + " ") or q.group.startswith(r.group + " "))
               for q in picked):
            picked.append(r)
        if len(picked) == n:
            break
    return tbl[tbl.key.isin([q.key for q in picked])].sort_values("cost", ascending=False)


def non_overlapping(rows, n):
    """Up to n tree rows, skipping any whose ancestor or descendant is already picked (they share games)."""
    picked = []
    for r in rows:
        if all(not (r.group.startswith(q.group + " ") or q.group.startswith(r.group + " ")) for q in picked):
            picked.append(r)
        if len(picked) == n:
            break
    return picked


def short_reason(text, words=12):
    """The first sentence of an explanation, at most `words` words."""
    text = re.sub(r"\s*\([^)]*\)", "", text)   # drop the parentheses: engine lines and evaluations
    first = re.split(r"(?<=[.!?])\s", text.strip(), maxsplit=1)[0].rstrip(".")
    toks = first.split()
    return first if len(toks) <= words else " ".join(toks[:words]).rstrip(",:;(") + "…"


PLAN_SIZE = 3
LEVEL_LOOKUPS = 12   # at most this many Explorer lookups while choosing the plan


def plan_items():
    """Up to three picks: recurring mistakes by points lost (not learned, not working at the player's level),
    then, if there are fewer, the weakest openings. [("mistake", p) | ("opening", row)]"""
    picks = []
    if ctx.analyzed:
        cand = by_cost([p for p in recurring([p for p in ctx.probs if p["status"] != "learned"]) if p["cost"] > 0.05])
        lookups = 0
        for p in cand:
            if C.lichess_token() and lookups < LEVEL_LOOKUPS:
                lookups += 1
                if (level_view(p) or {}).get("works"):
                    continue
            picks.append(("mistake", p))
            if len(picks) == PLAN_SIZE:
                return picks
    for r in focus_openings(PLAN_SIZE).itertuples():
        picks.append(("opening", r))
        if len(picks) == PLAN_SIZE:
            break
    return picks


def weak_item(r, tone):
    label, ctone = CONF[r.conf]
    err = (f' · טעות נפוצה: <span class="ltr">{esc(r.top_error)}</span> ב‑{r.top_error_count} משחקים'
           if r.top_error and r.top_error_count >= 2 else "")
    pill = f'<span class="badge b-{ctone}">{label}</span>' if r.conf == "low" else ""
    return (f'<div class="witem"><div class="card-h"><span class="t">{en(r.opening)}</span>{pill}</div>'
            f'<div class="moves" style="line-height:1.6">{esc(r.line)}</div>'
            f'<div class="note"><b style="color:var(--{tone})">{pct(r.score)}</b> לעומת ממוצע של {pct(r.base)} '
            f'(<span dir="ltr">{r.diff * 100:+.0f}%</span>) ב‑{r.games} משחקים{err}</div></div>')


def summary_list(t, picked, sign, tone):
    """Confident openings; when there are none, the two leading candidates, clearly marked as possibly chance."""
    if picked:
        return "".join(weak_item(r, tone) for r in picked)
    cand = t[(t["diff"] * sign > 0) & (t.games >= C.CONF_MID_GAMES)].sort_values("z", ascending=sign < 0)
    cand = non_overlapping(cand.itertuples(), 2)
    head = ("אין חולשה מובהקת." if sign < 0 else "אין חוזקה מובהקת.")
    if not cand:
        return f'<div class="note">{head} כל הפתיחות קרובות לממוצע.</div>'
    return (f'<div class="note">{head} הבולטות ביותר, שעדיין עשויות להיות מקריות:</div>'
            + "".join(weak_item(r, tone) for r in cand))


def short_name(r):
    """In tree view a child repeats its parent's name ("Vienna Game: Vienna Gambit" under "Vienna Game"): drop it."""
    tbl = ctx.tbl
    par = tbl[(tbl.color == r.color) & (tbl.group == r.parent)]
    pn = par.opening.iat[0] if len(par) else ""
    if pn and r.opening.startswith(pn + ": "):
        return r.opening[len(pn) + 2:]
    if pn and r.opening == pn:  # same name: show the moves this branch adds instead
        toks = r.group.split()
        k = max(int(par.plies.iat[0]), len(toks) - 2)
        return " ".join(move_label(i, m) if i % 2 or i == k + 1 else m for i, m in enumerate(toks[k:], k + 1))
    return r.opening


def last_plies(group, n=2):
    """The last `n` plies of a line with the move number: '4.d3 Nf6'."""
    toks = group.split()
    k = max(0, len(toks) - n)
    return " ".join(move_label(i, m) if i % 2 or i == k + 1 else m for i, m in enumerate(toks[k:], k + 1))


def node_games(op):
    """All filtered games that start with the node's moves (the node row sums its whole subtree)."""
    pre = op.group.split()
    fdf = ctx.fdf
    return fdf[(fdf.color == op.color) & fdf.line.str.split().map(lambda s: s[:len(pre)] == pre)]


def ordered_mistakes(items):
    """`items` with the plan's mistakes first (same order as the home page), then the rest by cost."""
    plan = [p for kind, p in plan_items() if kind == "mistake"]
    keys = {tr_key(p) for p in plan}
    return plan + [p for p in by_cost(items) if tr_key(p) not in keys]
