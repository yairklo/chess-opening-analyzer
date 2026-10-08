"""Full pipeline: download games (cached) -> Stockfish analysis -> print report. Use --refresh to re-download."""
import sys

from chessapp import fetch_games, analyze

if __name__ == "__main__":
    fetch_games.fetch("--refresh" in sys.argv)
    analyze.run()
