"""calibration — everything evalstats is forbidden to do.

evalstats computes numbers and raises; it never touches a file or prints. This
package is where reading, deciding what to run, and formatting live:

    loader.py    a CSV becomes a CalibrationData, and says what it did not find
    analysis.py  available columns decide which statistics are defensible
    report.py    results become markdown a person reads
"""

from . import analysis, loader, report

__all__ = ["analysis", "loader", "report"]
