PYTHON ?= python3.12

.PHONY: verify-hw06
verify-hw06:
	$(PYTHON) scripts/verify_hw06.py $(HW6_VERIFY_ARGS)
