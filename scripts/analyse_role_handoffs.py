"""Report role-pair coverage without treating inferred profiles as departments."""
import os
import sys
from pathlib import Path
for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ.setdefault(name,'1')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from orgmining.role_analysis import run
if __name__=='__main__':
    run()
