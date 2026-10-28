"""Installs the analysis file access audit in worker processes started by
paper/scripts/test_analysis.py (this folder is on their PYTHONPATH only while it runs)."""

import analysis_audit

analysis_audit.from_env()
