"""Host-managed Python script entry point, invoked by ui4me-run."""
import runpy
import sys
from pathlib import Path

if len(sys.argv) < 2:
    raise SystemExit('Expected a Python application path')
script = Path(sys.argv[1]).resolve()
sys.argv = [str(script), *sys.argv[2:]]
sys.path.insert(0, str(script.parent))
runpy.run_path(str(script), run_name='__main__')
