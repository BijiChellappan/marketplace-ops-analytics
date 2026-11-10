"""
One command to rebuild everything.

    python run_all.py           use the CSV files in data/csv/ (your data)
    python run_all.py --demo    first regenerate the synthetic demo data, then run

Steps: CSV -> SQLite -> SQL analyses -> catalog check -> experiment readout -> dashboard
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
steps = [["src/load_csv.py"], ["src/run_sql.py", "5"], ["src/catalog_check.py"],
         ["src/experiment_readout.py"], ["src/build_dashboard.py"]]
if "--demo" in sys.argv:
    steps.insert(0, ["data/generate_data.py"])

for step in steps:
    print(f"\n>>> python {' '.join(step)}")
    result = subprocess.run([sys.executable, *step], cwd=ROOT)
    if result.returncode != 0:
        sys.exit(f"Stopped: {step[0]} failed.")
print("\nDone. Open dashboard/index.html in a browser.")
