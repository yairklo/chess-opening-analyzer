"""Console summary of the analysis (numbers used in the final report)."""
import sqlite3
from chessapp import config as C
from chessapp.stats import load_results, opening_table, overall, problem_positions
df = load_results()
con = sqlite3.connect(C.DB_FILE)
sk = con.execute("select reason,count(*) from skipped group by reason").fetchall()
print("analyzed", len(df), "skipped", sk)
print("overall", overall(df))
print("plies analyzed mean", df.plies_analyzed.mean())
t = opening_table(df)
pd_opts = dict(index=False, float_format=lambda x: f"{x:.2f}")
print(t.drop(columns=["group"]).to_string(**pd_opts))
for c in ("white", "black"):
    print("==", c)
    for p in problem_positions(df, c):
        print(p["line"], "| n", p["count"], "| played", p["played"], "| best", p["best_san"], "| avgdrop", round(p["avg_drop"]), "| score", p["score"], "| explorer", bool(p.get("explorer")))
