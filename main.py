"""Single command-line entry point; run `python main.py --help`."""
import os
# Numerical libraries otherwise create a thread pool for every worker process.
for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(name, "1")
from orgmining.cli import main

if __name__ == "__main__":
    main()
