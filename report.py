"""Console summary of the analysis (numbers used in the final report)."""
import sqlite3
from chessapp import config as C
from chessapp.stats import load_results, occurrences, opening_table, overall, prepare, problem_positions
games, errors = load_results()
df, rel, tree = prepare(games, errors)
con = sqlite3.connect(C.DB_FILE)
sk = con.execute("select reason,count(*) from skipped group by reason").fetchall()
print("analyzed", len(df), "skipped", sk, "errors", len(errors))
print("overall", overall(df))
print("plies analyzed mean", df.plies_analyzed.mean())
t = opening_table(df, errors, tree)
pd_opts = dict(index=False, float_format=lambda x: f"{x:.2f}")
print(t[["color", "depth", "opening", "line", "games", "score", "cost", "early_error_share", "top_error",
         "top_error_count", "toxic"]].to_string(**pd_opts))
occ = occurrences(df)
for c in ("white", "black"):
    print("==", c)
    for p in problem_positions(df, rel, occ, c, min_games=C.MIN_PROBLEM_GAMES)[: C.TOP_POSITIONS]:
        print(p["opening"], "| n", p["count"], "| played", p["played"], "| best", p["best_san"], "| usual", p["usual"],
              "| win%", round(p["win_before"]), "->", round(p["win_after"]), "| score", round(p["score"], 2), "|", p["status"])
