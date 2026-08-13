PYTHON ?= $(shell python3 -c 'import pytest,yaml' >/dev/null 2>&1 && echo python3 || echo python)
TARGET ?= dev
CATALOG ?= cfihos_dev
DBX_PROFILE ?=
PROFILE_FLAG := $(if $(DBX_PROFILE),--profile=$(DBX_PROFILE),)

.PHONY: generate test lint bundle-validate verify acceptance acceptance-local

generate:
	$(PYTHON) src/parse_dictionary.py spec/C-DM-002-Data-Dictionary-V2.0.xlsx
	$(PYTHON) src/gen_ddl.py model/model.yml

test: generate
	$(PYTHON) -m pytest

lint:
	ruff check .

bundle-validate:
	databricks bundle validate -t $(TARGET) $(PROFILE_FLAG) --var="catalog=$(CATALOG)"

verify:
	databricks bundle deploy -t $(TARGET) $(PROFILE_FLAG) --var="catalog=$(CATALOG)"
	databricks bundle run load_rdl -t $(TARGET) $(PROFILE_FLAG) --var="catalog=$(CATALOG)"
	databricks bundle run validate -t $(TARGET) $(PROFILE_FLAG) --var="catalog=$(CATALOG)"

acceptance-local:
	$(PYTHON) -m pytest tests/test_acceptance.py

acceptance:
	@test -n "$(CFIHOS_ACCEPTANCE_CATALOG)" || (echo "Set CFIHOS_ACCEPTANCE_CATALOG to a fresh catalog name" && exit 2)
	databricks bundle deploy -t $(TARGET) $(PROFILE_FLAG) --var="catalog=$(CFIHOS_ACCEPTANCE_CATALOG)"
	databricks bundle run acceptance -t $(TARGET) $(PROFILE_FLAG) --var="catalog=$(CFIHOS_ACCEPTANCE_CATALOG)"
