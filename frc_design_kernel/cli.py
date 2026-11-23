"""The command line. Each command prints plain one-line messages saying what it did."""
import argparse

from .version import generator


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m frc_design_kernel", description="Build a preliminary robot design from a design source.")
    made = generator()
    parser.add_argument("--version", action="version", version=f"{made['library']} {made['version']} (commit {made['commit'] or 'unknown'})")
    parser.parse_args(argv)
    parser.print_help()
    return 0
