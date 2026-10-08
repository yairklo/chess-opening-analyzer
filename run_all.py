"""Full pipeline: download games (cached) -> Stockfish analysis. Usage: python run_all.py [user] [--refresh]"""
import sys

from chessapp import analyze, config as C, fetch_games

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    user = args[0] if args else C.USER
    fetch_games.fetch(user, "--refresh" in sys.argv)
    analyze.run(user)
