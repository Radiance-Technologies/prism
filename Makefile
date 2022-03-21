include Makefile.include

export

# build internal packages
.PHONY: install
install: venv_check venv
	echo "Installing project into virtual environment $(VENV)"
	SOFT=True make -C coqgym_interface install

# test internal packages
test: venv_check venv
	echo "Running tests"
	SOFT=True make -C coqgym_interface test

venv: $(VENV)/bin/activate

ifneq ($(SOFT),True)
.PHONY: requirements.txt
requirements.txt:
	touch requirements.txt
endif

ifneq ($(CONDA), True)
$(VENV)/bin/activate: requirements.txt
	test -d $(VENV) || virtualenv $(VENV) -p $(PEARLS_PYTHON)
	source $(VENV)/bin/activate && pip install -Ur requirements.txt
	touch $(VENV)/bin/activate
else
.PHONY: $(VENV)/bin/activate
$(VENV)/bin/activate: requirements.txt
	echo "Conda environment $(CONDA_DEFAULT_ENV) already activated."
endif


clean:
	if [ $(INVENV) = "True" ] ; then \
	  echo "You must deactivate your virtual environment prior to cleaning."; \
	  exit 1; \
	else \
	  echo "Removing virtual environment: $(VENV)"; \
	fi
	rm -rf $(VENV)
	find -iname "*.pyc" -delete
