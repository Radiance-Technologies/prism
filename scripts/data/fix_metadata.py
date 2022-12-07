"""
Sloppy script to fix metadata.
"""
from pathlib import Path
from typing import List

import tqdm
from seutil import io

from prism.project.metadata.storage import MetadataStorage
from prism.project.repo import ProjectRepo
from prism.util.swim.auto import AutoSwitchManager


def load_opam_projects() -> List[str]:
    """
    Load project names from opam_projects.txt.

    Returns
    -------
    List[str]
        Project names from opam_projects.txt
    """
    opam_projects_file_path = (
        Path(__name__).parent.resolve() / "dataset") / "opam_projects.txt"
    with open(opam_projects_file_path, "r") as f:
        projects_to_use = f.readlines()[1 :]
    return [p.strip() for p in projects_to_use]


if __name__ == "__main__":
    root_path = Path(__name__).parent.resolve().parent.resolve().parent.resolve(
    ) / "repos_full"
    mds_path = (
        Path(__name__).parent.resolve() / "dataset") / "agg_coq_repos.yml"
    md_storage = MetadataStorage.load(mds_path)
    n_build_workers = 16
    project_names = load_opam_projects()
    default_commits_path = (
        Path(__name__).parent.resolve() / "dataset") / "default_commits.yml"
    default_commits = io.load(default_commits_path, clz=dict)
    i = 0
    swim = AutoSwitchManager()
    for project_name in tqdm.tqdm(project_names):
        repo_path = root_path / project_name
        project = ProjectRepo(repo_path, md_storage, num_cores=n_build_workers)
        # project.infer_opam_dependencies()
        if default_commits[project_name]:
            project.git.checkout(default_commits[project_name][0])
        else:
            continue
        dependency_formula = project.get_dependency_formula("8.10.2")
        original_switch = project.opam_switch
        try:
            project.opam_switch = swim.get_switch(
                dependency_formula,
                variables={
                    'build': True,
                    'post': True,
                    'dev': True
                })
        except KeyboardInterrupt:
            raise
        except Exception as e:
            i += 1
            print(e)
            print(f"switch get exception {i}")
            continue
        try:
            project.infer_serapi_options()
        except KeyboardInterrupt:
            raise
        except Exception as e:
            i += 1
            print(e)
            print(f"infer serapi exception {i}")
            continue
        md_storage = project.metadata_storage
    MetadataStorage.dump(md_storage, mds_path)
