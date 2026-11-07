PYTHON ?= python3.12

.PHONY: verify-hw06
verify-hw06:
	$(PYTHON) scripts/verify_hw06.py $(HW6_VERIFY_ARGS)

.PHONY: verify-hw09
verify-hw09:
	PYTHONPATH=.:code $(PYTHON) scripts/verify_hw09.py $(HW9_VERIFY_ARGS)
