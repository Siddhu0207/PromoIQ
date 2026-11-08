"""Build blind review packet or score independently completed reviewer sheets."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from src.evaluation import create_packet,evaluate

ROOT=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=['prepare','score'])
    p.add_argument('--root',type=Path,default=ROOT)
    p.add_argument('--seed',type=int,default=301)
    p.add_argument('--set', dest='review_set', default='human_evaluation_v2',
                   choices=['human_evaluation','human_evaluation_v2'],
                   help='v2 is a new overlap-free review packet; v1 preserves your original reviewer sheets')
    p.add_argument('--overwrite',action='store_true',help='Explicitly replace reviewer sheets; back them up first')
    args=p.parse_args()
    result=create_packet(args.root,args.seed,args.overwrite,folder_name=args.review_set) if args.action=='prepare' else evaluate(args.root,folder_name=args.review_set)
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
