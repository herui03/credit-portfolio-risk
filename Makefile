# credit-portfolio-risk - one-command pipeline
#
# make demo   raw data -> warehouse -> profile -> limits -> verify
# make verify re-derive every figure cited in docs/ and fail on disagreement
#
# `verify` is the target that matters. Three findings on this project were
# plausible numbers with no error attached, and a test harness once reported
# "RUNS OK" while executing a comment. "It ran and looked sensible" is not
# evidence. Nothing here is trusted until verify is green.

PY := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: demo setup data build profile limits ewi stress excel tableau verify clean

demo: build profile limits ewi stress excel tableau verify

setup:
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

# Requires ~/.kaggle/kaggle.json (chmod 600). The token is never read by this
# repo - the kaggle CLI reads it itself. Do not put credentials in code.
data:
	mkdir -p data/raw
	cd data/raw && ../../.venv/bin/kaggle datasets download \
		-d wordsforthewise/lending-club -f accepted_2007_to_2018Q4.csv.gz

# Asserts: grain (1 row per loan), reject pattern (33 non-loan structural lines),
# live-book leak (0 closed loans). Fails the build rather than shipping a bad table.
build:
	$(PY) python/build_warehouse.py

profile:
	$(PY) python/profile_lendingclub.py

ewi:
	$(PY) python/ewi_monitor.py

stress:
	$(PY) python/stress_test.py

limits:
	$(PY) python/limit_monitor.py

excel:
	$(PY) python/build_excel_pack.py

tableau:
	$(PY) python/build_tableau_extracts.py

verify:
	$(PY) python/verify_claims.py

clean:
	rm -rf data/processed outputs/*.csv
