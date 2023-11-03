<!--
Copyright (c) 2023 Radiance Technologies, Inc.

This file is part of PRISM
(see https://github.com/orgs/Radiance-Technologies/prism).

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Lesser General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public
License along with this program. If not, see
<http://www.gnu.org/licenses/>.
-->
### Distribution Statement A (Approved for Public Release, Distribution Unlimited).
# PRISM

Code for the paper [Proof Repair Infrastructure for Supervised Models: Building a Large Proof Repair Dataset](https://drops.dagstuhl.de/opus/volltexte/2023/18401).

Please cite as
```
@inproceedings{reichel_proof_2023,
	address = {Dagstuhl, Germany},
	series = {Leibniz {International} {Proceedings} in {Informatics} ({LIPIcs})},
	title = {Proof {Repair} {Infrastructure} for {Supervised} {Models}: {Building} a {Large} {Proof} {Repair} {Dataset}},
	volume = {268},
	copyright = {All rights reserved},
	isbn = {978-3-95977-284-6},
	shorttitle = {Proof {Repair} {Infrastructure} for {Supervised} {Models}},
	url = {https://drops.dagstuhl.de/opus/volltexte/2023/18401},
	doi = {10.4230/LIPIcs.ITP.2023.26},
	urldate = {2023-07-27},
	booktitle = {14th {International} {Conference} on {Interactive} {Theorem} {Proving} ({ITP} 2023)},
	publisher = {Schloss Dagstuhl – Leibniz-Zentrum für Informatik},
	author = {Reichel, Tom and Henderson, R. Wesley and Touchet, Andrew and Gardner, Andrew and Ringer, Talia},
	editor = {Naumowicz, Adam and Thiemann, René},
	year = {2023},
	note = {ISSN: 1868-8969},
	keywords = {machine learning, proof repair, benchmarks, datasets, formal proof},
	pages = {26:1--26:20},
}
```

## Description

PRISM is a project management and data collection framework for the Coq
Proof Assistant geared towards enabling creation and curation of AI/ML
datasets for proof engineering tasks including proof repair.
Major subcomponents include virtual environment management through opam
switches, proof extraction utilities, and repair mining functions.


## Getting Started

### Prerequisites
PRISM only supports Unix hosts and has only been tested in Ubuntu 20.04
and Ubuntu 22.04, so this guide assumes access to a Linux terminal.
In addition, the following system packages or libraries must be installed:
* git
* make
* opam
* strace

### Workspace/Remote Environment Setup
* Navigate to top `prism` directory (the root of the repository).
* Create Python virtual environment (default version is 3.11.4).
  ```
  source setup_python.sh [Python 3 version (optional)]
  ```
* Install Coq (default version is 8.10.2).
  Note that you may need to run `opam init` to sucessfully install Coq.
  ```
  source setup_coq.sh [Coq version number (optional)]
  ```
* Install PRISM. Note that this requires one to have activated a virtual environment in
  the current shell (e.g., with `setup_python.sh` above).
  ```
  make install
  ```
  As a side-effect, this command will install and upgrade all PRISM installation dependencies,
  equivalent to `pip install -Ur requirements.txt`.
* Verify installation by running unit tests.
  Note that this requires one to have activated an OPAM switch in the current shell
  (e.g., with `setup_coq.sh`).
  ```
  make test
  ```
* Install development dependencies (linters, formatters, etc.) and pre-commit hooks.
  ```
  make dev
  ```
  Pre-commit hooks are automatically applied each time you try to commit changes and consist
  of a series of tests that must each pass before the commit is added to the repository's index.
  Some of these hooks may modify files (e.g., applying code styles).
  Any changes induced by the hooks must be manually staged for commit via `git add` before
  attempting to `git commit` again.
  Pre-commit hooks may be skipped by adding the `--no-verify` option to `git commit`.
  However, skipping the hooks is generally discouraged since it merely delays the inevitable;
  server-side pre-commit hooks will be applied in any branch for which a merge request has been
  created and force pipeline failures (and thus prevent merges) until the hooks are satisfied.
  Only an administrator, project owner, or maintainer can bypass these server-side hooks when
  the target branch is protected.

### Integrated Development Environment Setup
Visual Studio Code with the following minimal extensions installed and enabled is the _recommended_ IDE:
* [Remote Development](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.vscode-remote-extensionpack),
  [Remote - SSH](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh): For
  developing remotely on Radiance servers.
  Follow the [official guide](https://code.visualstudio.com/docs/remote/ssh) to set up SSH keys for
  password-less authentication.
* [Remote - WSL](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-wsl): For
  developing locally in the Windows Subsystem for Linux.
* [Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python),
  [Pylance](https://marketplace.visualstudio.com/items?itemName=ms-python.vscode-pylance): For developing
  Python packages and scripts.
  One should configure the extension to use `yapf` and `flake8` as the formatting and linting providers,
  respectively, with linting set to run upon saving of a file.
  A file may be manually formatted by opening the command palette with <kbd>F1</kbd> and selecting `Format Document`.
  Imports may also be sorted through the `Python Refactor: Sort Imports` command in the command palette.
  Static type checking should also be enabled with `mypy`.
* [VSCoq](https://marketplace.visualstudio.com/items?itemName=maximedenes.vscoq): For syntax highlighting
  of Coq source files and possible eventual integration in Phase 2.
* [GitLens](https://marketplace.visualstudio.com/items?itemName=eamodio.gitlens): For viewing line-by-line
  history while editing.
* [Trailing Whitespace](https://marketplace.visualstudio.com/items?itemName=jkiviluoto.tws): For visualizing
  and removing trailing whitespace on save.
  The extension settings should be configured to highlight the trailing whitespace and trim it on save.
* [autoDocstring](https://marketplace.visualstudio.com/items?itemName=njpwerner.autodocstring): For automatically
  generating docstring stubs from type hints.
  One should ensure that the extension settings are configured to use the `numpy` format, use `"""` quote style,
  start the docstring on a new line, and to **not** include the function name at the start of the docstring.
* [select highlight in minimap](https://marketplace.visualstudio.com/items?itemName=mde.select-highlight-minimap): For
  better visibility of selections in the minimap.

In addition, one is recommended to set the following variables in their settings JSON:
`"editor.rulers": [72, 80, 88]` and
`"python.defaultInterpreterPath": "path/to/prism/venv-X.Y.Z/bin/pythonX.Y"`
with the latter appropriately modified to match the location of the preferred Python interpreter.

## A Brief Guide to the Source Code
Docstrings are generally expected to give a sufficient explanation of
contents and functionality within PRISM source code.
Users are encouraged to explore on their own.
Some highlights are listed below:
* [Project](prism/project/base.py): The `Project` class is the central
figure of PRISM, integrating operations including building, debugging,
and dependency management.
`Project` includes methods for inferring [metadata](prism/project/metadata/dataclass.py), enumerating project file, and [parsing](prism/language/heuristic/parser.py) Coq sentences from project files.
In practice, one will likely use [`ProjectRepo`](prism/project/repo.py) objects
to work with Coq projects.
* [Project metadata](prism/project/metadata/dataclass.py): Metadata supplies
configuration information for a `Project` including build commands,
dependencies, and options for line-by-line execution with [`SerAPI`](prism/interface/coq/serapi.py).
* [Metadata storage](prism/project/metadata/storage.py): Metadata for multiple
commits or projects is aggregated in a `MetadataStorage` object, which can enumerate the stored metadata and perform insertion, update, and retrieval
operations.
A [serialized example](dataset/metadata.yml) covering the projects in the
dataset can be loaded with `MetadataStorage.load`.
* [SerAPI](prism/interface/coq/serapi.py): Originally based on the [`SerAPI`
class of CoqGym](https://github.com/princeton-vl/CoqGym/blob/a739d99cdf5b0451dd8a362d3c541ca3b66112d3/serapi.py#L64), this class provides
a wrapper around the `sertop` executable of [`coq-serapi`](https://github.com/ejgallego/coq-serapi) and provides tested support for 7 minor versions of Coq
ranging from 8.9 to 8.15.
* [Command extractor](prism/data/cache/command_extractor.py): A higher-level
wrapper around `SerAPI` that tracks document context and aggregates proofs into
objects with abstract syntax trees (ASTs), goals, hypotheses, and fully
qualified identifiers.
The `CommandExtractor` provides more straightforward rollback mechanisms than
`SerAPI`.
* [Cache types](prism/data/cache/types): Caches are constructed in the first
phase of repair mining that contain detailed context for each command in a
project commit.
The data for a project commit is stored in an aptly named `ProjectCommitData`,
which captures the build environment for reproduction in addition to the
comments and commands of each file.
A `ProjectCommitData` can be dumped to file using
`ProjectCommitData.write_coq_project` to reproduce the raw text of
the commit's Coq files.
* [Repair example datatypes](prism/data/repair/instance.py): Repair examples are
constructed in the second phase of repair mining, which operates over the cached commits.
A generic `RepairInstance` class provides the core structure of a repair example as an
erroneous project state (and `ErrorInstance`) paired with a repair.
Two concrete subclasses, `GitRepairInstance` and `ProjectCommitDataRepairInstance`,
specialize the base class to Git diffs with commit SHAs and `ProjectCommitDataDiff`s with
`ProjectCommitData`s, respectively.
The former provide standalone representations of repairs whereas the latter require
`prism` to efficiently operate.
Methods to construct each are provided.
* [opam](prism/util/opam/api.py): A basic Python API for interacting with
[`opam`](https://opam.ocaml.org/), enabling the creation, deletion, and *cloning* of switches.
Note that cloned switches can only be used through the Python API (namely the
[`OpamSwitch`](prism/util/opam/switch.py) class) as `opam` is ignorant of them.
* [opam switch](prism/util/opam/switch.py): An abstraction of an `opam` switch,
or virtual environment/sandbox, in which a project can be built in isolation.
Enables the installation and removal of dependencies.
Note that if the `OpamSwitch` represents a clone, then the `opam`-managed
original switch must not be deleted until the clone is no longer needed.
* [Switch manager](prism/util/opam/swim.py): The switch manager (SwiM) provides
switches upon request from a managed pool that satisfy given constraints.
For example, if one wants a switch with a certain set of packages installed, the
SwiM will find the closest switch in its pool to satisfying the requirements, clone it,
install the packages, and return another clone that will be entirely owned by the
caller.
The first clone is added to the managed pool in anticipation of accelerating subsequent
requests.
A least-recently-used (LRU) cache evicts stale switches that have not been requested
frequently.
Multiple flavors of `SwitchManager` are provided, but the
[`AutoSwitchManager`](prism/util/swim/auto.py) is the easiest to use and
implements the features described above.
\
\
**Warning** The SwiM can easily and quickly consume disk space.
To clear the auto-generated switch clones, run `rm -rf /path/to/your/opam/root/*_clone_*`.
\
\
**Warning** The SwiM assumes complete control of the `opam` root.
It is not safe to perform normal `opam` operations or operate two SwiMs at once on the
same root directory.
The [`SharedSwitchManager`](prism/util/swim/shared.py) provides a multiprocessing-safe
implementation.


### Scripts
Standalone scripts that provide both core and superficial utilities are
housed in the [`scripts`](scripts) directory.
Note that these scripts lie outside CI and are not necessarily
maintained.

Some important scripts are highlighted here.
* [Cache extraction](scripts/data/extract_cache.py): Perform
[cache extraction](#cache-extraction)
* [Repair mining](scripts/data/mine_repair_instances.py): Perform
[repair mining](#repair-mining) on an extracted cache of project commit data.
* [Repair example filtering](scripts/data/filter_repair_examples.py): Recursively scan a
directory for repair instances matching one or more tags and either print a list of found
files or simply count them.

## Performing repair mining
The primary purpose of PRISM is to enable mining of proof repairs from Git repositories.
The following steps are recommended to perform repair mining (after
following the directions in [Getting Started](#getting-started)).
Repair mining is divided into two phases: cache extraction and repair
mining.

### Cache Extraction
In the cache extraction phase, we iterate over the commits of one or
more projects and independently attempt to build them before extracting
line-by-line context.
The ultimate output for a given commit is a
[`ProjectCommitData`](prism/data/cache/types/project.py).
The cache files are stored in a directory structure defined by the
[`CoqProjectBuildCacheProtocol`](prism/data/cache/server.py).
The [`extract_cache.py`](scripts/data/extract_cache.py) script is the
main entrypoint for cache extraction and will handle creation of a base
pool of switches for a SwiM to use.
Arguments to the script allow one to limit extraction to a subset of
projects, Coq versions, commits, or files.
See the script's help message for more details.

Builds are attempted for supported Coq versions in reverse order.
Extraction of a large number of projects or commits can take a very long
time, so it is recommended that one uses a terminal multiplexer such as `tmux`.
Progress can be monitored in a separate shell with the
[`monitor-caching.py`](scripts/data/monitor-caching.py), which will show the
number of successful and failed extractions.
Do not be alarmed by a large number of failures (shown as errors), as some
commits simply cannot be extracted.

Failures are grouped into three categories: build errors, cache errors,
and miscellaneous errors.
These errors may be treated as symptoms; determination of the underlying
cause of failure is a manual procedure.
Build errors indicate that something went wrong during a build process and
may indicate either a buggy project commit *or* incorrect metadata that could
not be repaired by builtin inference mechanisms.
Cache errors imply a bug in the extraction code itself, either from a flawed
assertion/assumption or some other logical error.
Cache errors are the only category indicative of something unambiguously wrong,
but each such error generally impacts only a subset of commits.
Miscellaneous errors are captured exceptions that do not fall within the
previous two categories.
Failure to obtain a switch from the SwiM due to unsatisfiable dependencies is a common
miscellaneous error, which may or may not be indicative of flawed metadata.

If extraction of a project commit encountered an error, one can open the error
log in the cache to obtain a stack trace, which may also identify the Coq file and
line at which the error occurred.
Running [extraction](scripts/data/extract_cache.py) limited to just the project,
commit, Coq version, and file enables one to use a debugger to more precisely
identify the cause and possible fixes.

Extraction contains multiprocessing components across projects and files,
so be sure that the number of workers chosen is appropriate for your available
resources.
In addition, be prepared for a significant consumption of disk space from
cloned switches created by the SwiM.
Finally, note that even though `--max-proj-build-runtime X` will abort an extraction
if the project takes more than `X` seconds to build, a timeout on the actual
extraction of commands via line-by-line execution may last longer.


### Repair Mining
In the repair mining phase, we consider pairs of extracted commits and mine
repairs from their changes.
The ultimate output is a collection of pairs of files, each storing a serialized
[`GitRepairInstance`](prism/data/repair/instance.py) and
[`ProjectCommitDataRepairInstance`](prism/data/repair/instance.py), respectively.
The [`mine_repair_instances.py`](scripts/data/mine_repair_instances.py) script is the
main entrypoint for repair mining and takes a configuration file as its only argument.
A sample configuration is provided by
[`mine_repair_instances`](scripts/data/mine_repair_instances_default_config.json).
Note that one should adjust the `cache_root`, `repair_instance_db_directory`, and
`metadata_storage_file` to match the working directory when the repair mining script
is called.
In order to prevent successive repair mining runs from clobbering one another,
especially when there have been changes to `prism`, it is recommended that one first
generate a configuration with [`produce_config.py`](scripts/data/produce_config.py),
which will generate a base configuration file with the current commit as the name
of the root directory.
The configuration file simply stores a JSON dictionary containing keyword arguments
to the [`repair_mining_loop`](prism/data/repair/mining.py), where one can find
a description for each.

Repair mining contains multiprocessing components and loading large files into memory,
so be sure that the number of workers chosen is appropriate for your available
resources.
Choosing too many workers may result in difficult-to-debug out-of-memory errors.
Note that `fast` is enabled by default in generated configurations, which strips the
loaded caches (and resulting `ProjectCommitDataRepairInstance`s) of ASTs and other
expensive to process/store data.

One may wish to perform repair mining on (disjoint) caches on one or more computers.
Repair instance databases produced in this manner can be merged after the fact using
the [`merge_repair_instance_dbs.py`](scripts/data/merge_repair_instance_dbs.py) script,
which will deduplicate any repairs in their intersection.

Some basic summary statistics can be collected using the
[`filter_repair_examples.py`](scripts/data/filter_repair_examples.py).
For example, one may count the total number of repair examples in a database with a
given (set of) tag(s).
Tags of particular importance include `repair:proof` and `repair:specification`.
The former indicates a repair to the body of a proof, whereas the latter indicates a
repair to a lemma/conjecture itself.
Cataloguing repairs based on the type of Vernacular command
(e.g., `VernacStartTheoremProof`) can be done using tags of the form
`repair:[CommmandTypeName]`, e.g., `repair:VernacDefinition`.


## Acknowledgements
This work was supported by the Defense Advanced Research Projects Agency (DARPA)
under Agreement HR00112290067.

The views, opinions, and/or findings expressed are those of the authors and should not be
interpreted as representing the official views or policies of the Department of Defense
or the U.S. Government.
