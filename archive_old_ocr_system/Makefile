VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
REQ := requirements.txt
VIDEO ?=

.PHONY: help venv install dry split

help:
	@echo "make venv        # create virtualenv"
	@echo "make install     # install Python deps"
	@echo "make dry VIDEO=path/to/file.mkv   # analyze only (no cutting)"
	@echo "make split VIDEO=path/to/file.mkv  # full pipeline with cuts"

venv:
	python3 -m venv $(VENV)

install: venv $(REQ)
	$(PIP) install --upgrade pip
	$(PIP) install -r $(REQ)

# Dry analysis (detect scenes/intro/OCR), no output files written
# Usage: make dry VIDEO=yourfile.mkv [ASSUME_TWO=1]
dry: check-video
	$(PYTHON) pipeline.py "$(VIDEO)" $(if $(ASSUME_TWO),--assume-two,) --no-split --verbose

# Full pipeline: detect and cut episodes/intros
# Usage: make split VIDEO=yourfile.mkv [ASSUME_TWO=1]
split: check-video
	$(PYTHON) pipeline.py "$(VIDEO)" $(if $(ASSUME_TWO),--assume-two,) --verbose

check-video:
	@if [ -z "$(VIDEO)" ]; then echo "VIDEO is required"; exit 1; fi
