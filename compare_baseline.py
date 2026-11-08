"""Run first-40-second baseline evidence comparison across parsed scripts."""
from pathlib import Path
import json
from src.baseline import calculate
if __name__=='__main__':
    r=calculate(Path(__file__).resolve().parent)
    print(json.dumps(r['outcomes'],indent=2))
