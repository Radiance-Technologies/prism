## Project Metadata Specifications

Specifies fields or attributes for `ProjectMetadata` class. Fields defined in the following specification (unless ammended by unanimity) should be considered valid, complete and not subject to change. The required fields are:


Instances of `ProjectMetadata` are metadata objects.


### Specification Attributes and Parameters: 

- **`project_name: str`**

     The unique name of the project in the dataset either literal or derived from several auxiliary identifiers.
    
    
- **`project_url: Optional[str]`**

     If available, this is the URL hosting the authoritative source code or repository (e.g., Git) of a particular project in the dataset.
     If not given, then this metadata is interpreted as the default for the project regardless of origin unless overridden by a metadata record specifying a `project_url`.
    
    
- **`commit_sha: Optional[str]`**

     If available, this can be a Git object hash or a local project SHA. It serves as an additional identifier for a project (in a particular version) in the dataset. 
     A comparison with the SHA of the first commit on the master branch will be necessary for ensuring the uniqueness of the project identifier.
     The commit must be null if `project_url` is null. 
     If the commit is null, then this metadata is interpreted as the default for the indicated repository unless overridden by a metadata record specifying a `commit_sha`.
    
    
- **`ignore_path_regex: List[str]`**

     Prevents inclusion of inter-project dependencies that are included as submodules or subdirectories (such as `CompCert` and `coq-ext-lib` in VST). 
     Special consideration must be given to these dependencies as they affect canonical splitting of training, test and validation datasets affecting the performace of the target ML model.
    

- **`coq_version: str`**

     Version of the Coq Proof Assistant used to build this project. 
     This field provides support for datasets containing commits across multiple Coq versions. 
     

- **`serapi_version:str`**

     Version of the API that serializes Coq internal OCaml datatypes from/to *S-expressions* or JSON. 
     A version of SerAPI must be installed to parse documents for repair.
     The version indicated must be compatible with the specified `coq_version`.   
    

- **`serapi_options: str`**

     Flags or options passed to the SerAPI Coq compiler `sercomp`, the Coq tokenizer `sertok`, or the Coq Top level compiler with Serialization Support `sertop`.    
    
    
- **`coq_dependencies: List[str]`**

     List of dependencies on packages referring to Coq formalizations and plugins that are packaged using OPAM and whose installation is required to build this project.
     A name `name` in `coq_dependencies` should be given such that `opam install name` results in installing the named dependency.
     Coq projects are often built or installed using `make` and `make install` under the assumption of an existing `Makefile` for the Coq project in dataset, but the `coq_dependencies` are typically assumed to be installed prior to running `make`.
     Only dependencies that are not handled by the project's build system should be listed here.
     
    
- **`opam_repos: List[str]`**

     Specifies list of OPAM repositories typically managed through the command `opam-repository`. 
     An OPAM repository hosts packages that may be required for installation of this project.
     Repositories can be registered through subcommands `add`, `remove` and `set-url`, and are updated from their URLs using `opam update`.
     This field is expected to be rarely used.
    
    
- **`opam_dependencies: List[str]`**
 
     List of non-Coq OPAM dependencies whose installation is required to build the project. 
     A name `name` in `opam_dependencies` should be given such that `opam install name` results in installing the named dependency.
     Coq projects are often built or installed using `make` and `make install` under the assumption of an existing `Makefile` for the Coq project in dataset, but the `coq_dependencies` are typically assumed to be installed prior to running `make`.
     Only dependencies that are not handled by the project's build system should be listed here.
     This field is expected to be rarely used.
    

- **`build_cmd: List[str]`**

     Specifies a list of commands for this project (e.g., `build.sh` or `make`) that result in building (compiling) the Coq project.
     Commands are presumed to be executed in a shell, e.g., Bash.
    
    
- **`install_cmd: List[str]`**

     Specifies a list of commands for this project (e.g., `install.sh` or `make install`) that result in installing the Coq project to the user's local package index, thus making the package available for use as a dependency by other projects.
     The project may be presumed to have been built using `build_cmd` before the sequence of commands in `install_cmd`.
     Commands are presumed to be executed in a shell, e.g., Bash.
    
    
- **`clean_cmd: List[str]`**

     Specifies a list of commands for removing executables, object files, and other artifacts from building the project (e.g., `make clean`).
     Commands are presumed to be executed in a shell, e.g., Bash.

