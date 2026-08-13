# Engineer and CI targets. Workspace users should start with notebooks/00_get_started.py.
PYTHON ?= $(shell python3 -c 'import pytest,yaml' >/dev/null 2>&1 && echo python3 || echo python)
TARGET ?= dev
CATALOG ?= cfihos_dev
DBX_PROFILE ?=
PROFILE_FLAG := $(if $(DBX_PROFILE),--profile=$(DBX_PROFILE),)

.PHONY: generate test lint bundle-validate acceptance

generate:
	$(PYTHON) src/parse_dictionary.py spec/C-DM-002-Data-Dictionary-V2.0.xlsx
	$(PYTHON) src/gen_ddl.py model/model.yml

test: generate
	$(PYTHON) -m pytest
	$(PYTHON) tests/check_sources.py

lint:
	ruff check .

bundle-validate:
	databricks bundle validate -t $(TARGET) $(PROFILE_FLAG) --var="catalog=$(CATALOG)"

acceptance:
	@test -n "$(CFIHOS_ACCEPTANCE_CATALOG)" || (echo "Set CFIHOS_ACCEPTANCE_CATALOG to a fresh catalog name" && exit 2)
	databricks bundle deploy -t $(TARGET) $(PROFILE_FLAG) --var="catalog=$(CFIHOS_ACCEPTANCE_CATALOG)"
	databricks bundle run acceptance -t $(TARGET) $(PROFILE_FLAG) --var="catalog=$(CFIHOS_ACCEPTANCE_CATALOG)"
