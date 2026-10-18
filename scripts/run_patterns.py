import sys
import os
for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[name]="1"
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from orgmining.patterns import run
if __name__ == '__main__':
    run()
