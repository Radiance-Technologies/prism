include Makefile.include

export

# build internal packages
.PHONY: install
install: venv_check venv
	echo "Installing project into virtual environment $(VENV)"
	pip install -e .

# test internal packages
test: test_none test_8_9_1 test_8_10_2 test_8_11_2 test_8_12_2 test_8_13_2 test_8_14_1 test_8_15_2

test_none: venv_check venv
	echo "Running tests that don't need any particular Coq version (using default Coq 8.10.2)"
	source setup_coq.sh 8.10.2 -n && \
	pytest --durations=0 \
	    --durations-min=1.0 \
	    --pyargs \
	    --cov=prism -m "not coq_all \
	                    and not coq_8_9_1 \
	                    and not coq_8_10_2 \
	                    and not coq_8_11_2 \
	                    and not coq_8_12_2 \
	                    and not coq_8_13_2 \
	                    and not coq_8_14_1 \
	                    and not coq_8_15_2" \
		prism

test_8_9_1: venv_check venv
	echo "Running tests for Coq 8.9.1"
	source setup_coq.sh 8.9.1 -n && \
	pytest --durations=0 \
	    --durations-min=1.0 \
	    --pyargs \
	    --cov=prism -m "coq_all \
	                    or coq_8_9_1" \
		prism

test_8_10_2: venv_check venv
	echo "Running tests for Coq 8.10.2"
	source setup_coq.sh 8.10.2 -n && \
	pytest --durations=0 \
	    --durations-min=1.0 \
	    --pyargs \
	    --cov=prism -m "coq_all \
	                    or coq_8_10_2" \
		prism

test_8_11_2: venv_check venv
	echo "Running tests for Coq 8.11.2"
	source setup_coq.sh 8.11.2 -n && \
	pytest --durations=0 \
	    --durations-min=1.0 \
	    --pyargs \
	    --cov=prism -m "coq_all \
	                    or coq_8_11_2" \
		prism

test_8_12_2: venv_check venv
	echo "Running tests for Coq 8.12.2"
	source setup_coq.sh 8.12.2 -n && \
	pytest --durations=0 \
	    --durations-min=1.0 \
	    --pyargs \
	    --cov=prism -m "coq_all \
	                    or coq_8_12_2" \
		prism

test_8_13_2: venv_check venv
	echo "Running tests for Coq 8.13.2"
	source setup_coq.sh 8.13.2 -n && \
	pytest --durations=0 \
	    --durations-min=1.0 \
	    --pyargs \
	    --cov=prism -m "coq_all \
	                    or coq_8_13_2" \
		prism

test_8_14_1: venv_check venv
	echo "Running tests for Coq 8.14.1"
	source setup_coq.sh 8.14.1 -n && \
	pytest --durations=0 \
	    --durations-min=1.0 \
	    --pyargs \
	    --cov=prism -m "coq_all \
	                    or coq_8_14_1" \
		prism

test_8_15_2: venv_check venv
	echo "Running tests for Coq 8.15.2"
	source setup_coq.sh 8.15.2 -n && \
	pytest --durations=0 \
	    --durations-min=1.0 \
	    --pyargs \
	    --cov=prism -m "coq_all \
	                    or coq_8_15_2" \
		prism

.PHONY: dev
dev: venv_check venv
	echo "Installing developer requirements"
	pip install -Ur requirements/dev.txt
	echo "Installing pre-commit hooks"
	pre-commit install

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

ifdef OPAMSWITCH
switch_check:
else
switch_check:
	$(error You must activate an OPAM switch before making this target. $(n)    \
	  Call 'source $(GITROOT)/setup_coq.sh' to install the project switch)
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
	opam switch remove $(SWITCH_NAME)
