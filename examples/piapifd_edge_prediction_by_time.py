"""Run the MySQL prediction example for an explicit source-local [from, to) range.

All rows in the range are processed in batches unless --limit is supplied.
Preview is the default; pass --mode write to save predictions to piapifd_edge.
The shared client defaults to target table pidata1_predict and reads the same
explicit feature-alias configuration as the whole-table entrypoint.
Both entrypoints read piapifd_prediction.ini or a file selected with --config.
Credentials use the same client .env.local, or a file selected with --env-file.
"""
import sys

if __package__:
    from .piapifd_edge_prediction import main
else:
    from piapifd_edge_prediction import main


if __name__ == '__main__':
    sys.exit(main(require_time_range=True))
