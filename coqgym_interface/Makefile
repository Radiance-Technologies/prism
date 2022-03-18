include ../Makefile.include

install: venv_check venv
	pip install -e .

test: venv_check venv
	pushd test && pytest --cov=$(PACKAGE) && popd

venv:
	make -C .. venv

clean:
	find -iname "*.pyc" -delete
