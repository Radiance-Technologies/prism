# PRISM

Pretraining for Proof Repair with Imposed Syntax Modeling

## Description

PRISM is a framework to enable the augmentation of pretrained language models (LMs) with syntactical
and semantic relational knowledge captured via graph neural networks (GNNs) for efficient proof
generation and repair with limited data.
The LM aids in the generation of well-structured code while reinforcement learning (RL) ensures proof
correctness and localization.
PRISM will culminate in a prototype IDE extension that uses the developed machine learning (ML) model
to propose proofs or proof(-related) repairs for regions of code prompted by the user.


## Getting Started

### Workspace/Remote Environment Setup
* Navigate to top `prism` directory
* Create Python virtual environment (default version is 3.9.10)
  ```
  source setup_python.sh [Python 3 version (optional)]
  ```
* Install Coq (default version is 8.10.2, alternative versions not currently supported)
* May need to run `opam init` to sucessfully install Coq
<<<<<<< HEAD
  ```
  source setup_coq.sh
  ```
* Install PRISM. Note that this requires one to have activated a virtual environment in the current shell (e.g., with `setup_python.sh` above).
  ```
  make install
  ```
  As a side-effect, this command will install and upgrade all PRISM installation dependencies, equivalent to `pip install -Ur requirements.txt`.
* Verify installation by running unit tests. Note that this requires one to have activated an OPAM switch in the current shell (e.g., with `setup_coq.sh`)/
  ```
  make test
  ```
* Install development dependencies (linters, formatters, etc.) and pre-commit hooks.
  ```
  make dev
  ```
  Pre-commit hooks are automatically applied each time you try to commit changes and consist of a series of tests that must each pass before the commit is added to the repository's index.
  Some of these hooks may modify files (e.g., applying code styles).
  Any changes induced by the hooks must be manually staged for commit via `git add` before attempting to `git commit` again.
  Pre-commit hooks may be skipped by adding the `--no-verify` option to `git commit`.
  However, skipping the hooks is generally discouraged since it merely delays the inevitable; server-side pre-commit hooks will be applied in any branch for which a merge request has been created and force pipeline failures (and thus prevent merges) until the hooks are satisfied.
  Only an administrator, project owner, or maintainer can bypass these server-side hooks when the target branch is protected.

### Integrated Development Environment Setup
Visual Studio Code with the following minimal extensions installed and enabled is the _recommended_ IDE:
* [Remote Development](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.vscode-remote-extensionpack), [Remote - SSH](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh): For developing remotely on Radiance servers. Follow the [official guide](https://code.visualstudio.com/docs/remote/ssh) to set up SSH keys for password-less authentication.
* [Remote - WSL](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-wsl): For developing locally in the Windows Subsystem for Linux.
* [Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python), [Pylance](https://marketplace.visualstudio.com/items?itemName=ms-python.vscode-pylance): For developing Python packages and scripts.
  One should configure the extension to use `yapf` and `flake8` as the formatting and linting providers, respectively, with linting set to run upon saving of a file.
  A file may be manually formatted by opening the command palette with <kbd>F1</kbd> and selecting `Format Document`.
  Imports may also be sorted through the `Python Refactor: Sort Imports` command in the command palette.
* [VSCoq](https://marketplace.visualstudio.com/items?itemName=maximedenes.vscoq): For syntax highlighting of Coq source files and possible eventual integration in Phase 2.
* [GitLens](https://marketplace.visualstudio.com/items?itemName=eamodio.gitlens): For viewing line-by-line history while editing.
* [Trailing Whitespace](https://marketplace.visualstudio.com/items?itemName=jkiviluoto.tws): For visualizing and removing trailing whitespace on save.
  The extension settings should be configured to highlight the trailing whitespace and trim it on save.
* [autoDocstring](https://marketplace.visualstudio.com/items?itemName=njpwerner.autodocstring): For automatically generating docstring stubs from type hints.
  One should ensure that the extension settings are configured to use the `numpy` format, use `"""` quote style, start the docstring on a new line, and to **not** include the function name at the start of the docstring.
* [select highlight in minimap](https://marketplace.visualstudio.com/items?itemName=mde.select-highlight-minimap): For better visibility of selections in the minimap.
=======
```
source setup_coq.sh
```
* Install additional dependencies in virtual environment
```
pip install -r requirements.txt
```
>>>>>>> d7e6fd32488879098d8003e4993e5fc6bf7e9b62
