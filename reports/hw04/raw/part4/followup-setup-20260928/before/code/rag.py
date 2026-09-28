#!/usr/bin/env python3
"""HW4 Part 4: explicit local setup, development, and frozen A/B/C experiments."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['download-model','download-tokenizer','inspect','pilot','run'])
    p.add_argument('--output',help='New evidence directory; existing paths are never overwritten')
    p.add_argument('--config')
    p.add_argument('--embedding-cache')
    args=p.parse_args()
    from src.rag.runner import ROOT,INPUTS,read_yaml,execute
    if args.command=='download-tokenizer':
        from huggingface_hub import snapshot_download
        spec=read_yaml(args.config or INPUTS/'experiment_config.yaml')['generator_tokenizer']
        cache=Path(spec['cache'])
        if not cache.is_absolute(): cache=ROOT/cache
        print(snapshot_download(spec['model'],revision=spec['revision'],cache_dir=str(cache),
              allow_patterns=['tokenizer.json','tokenizer_config.json','vocab.json','merges.txt','config.json']))
        return
    if args.command=='download-model':
        from src.retrieval.embedding import download_model
        config=read_yaml(args.config or INPUTS/'experiment_config.yaml')
        cache=Path(args.embedding_cache or config['embedding_cache'])
        if not cache.is_absolute(): cache=ROOT/cache
        print(download_model(config,cache)); return
    if not args.output: p.error('--output is required')
    print(execute(args.command,args.output,args.config,args.embedding_cache))


if __name__=='__main__':
    main()
