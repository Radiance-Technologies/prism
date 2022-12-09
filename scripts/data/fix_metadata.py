"""
Script to fix metadata.
"""
from argparse import ArgumentParser, Namespace
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


def main(args: Namespace):
    """
    Carry out metadata inference tasks as specified by args.

    Parameters
    ----------
    args : Namespace
        Script arguments
    """
    root_path = Path(args.root_path)
    mds_path = Path(args.mds_path)
    default_commits_path = Path(args.default_commits_path)
    coq_version: str = args.coq_version
    md_storage = MetadataStorage.load(mds_path)
    n_build_workers: int = args.num_build_workers
    project_names = load_opam_projects()
    default_commits = io.load(default_commits_path, clz=dict)
    i = 0
    swim = AutoSwitchManager()
    if not (args.infer_opam_dependencies or args.infer_serapi_options):
        print(
            'Nothing to do. Specify one or both of '
            '"--infer-opam-dependencies" and "--infer-serapi-options".')
        return
    pbar = tqdm.tqdm(project_names)
    for project_name in pbar:
        repo_path = root_path / project_name
        project = ProjectRepo(repo_path, md_storage, num_cores=n_build_workers)
        if args.infer_opam_dependencies:
            pbar.set_description(f"Infer opam deps for project {project_name}")
            project.infer_opam_dependencies()
        if not args.infer_serapi_options:
            # Nothing else to do; continue
            continue
        if default_commits[project_name]:
            project.git.checkout(default_commits[project_name][0])
        else:
            continue
        dependency_formula = project.get_dependency_formula(coq_version)
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
            pbar.set_description(
                f"Infer serapi opts for project {project_name}")
            project.infer_serapi_options()
        except KeyboardInterrupt:
            raise
        except Exception as e:
            i += 1
            print(e)
            print(f"infer serapi exception {i}")
            continue
        md_storage = project.metadata_storage
    if not args.dry_run:
        MetadataStorage.dump(md_storage, mds_path)


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "--root-path",
        default=str(
            Path(__name__).parent.resolve().parent.resolve().parent.resolve()
            / "repos_full"),
        help="Path to coq project repositories root folder")
    parser.add_argument(
        "--mds-path",
        default=str(
            (Path(__name__).parent.resolve() / "dataset")
            / "agg_coq_repos.yml"),
        help="Path to project metadata storage file")
    parser.add_argument(
        "--default-commits-path",
        default=str(
            (Path(__name__).parent.resolve() / "dataset")
            / "default_commits.yml"),
        help="Path to yaml file containing default commits for projects")
    parser.add_argument(
        "--coq-version",
        default="8.10.2",
        help="Coq version to specify when creating switch for inferring serapi"
        " options.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="If this flag is used, new metadata will not be saved; the old"
        " file will remain as-is.")
    parser.add_argument(
        "--num-build-workers",
        default=16,
        type=int,
        help="Number of workers to use when building and inferring serapi"
        " options.")
    parser.add_argument(
        "--infer-serapi-options",
        action="store_true",
        help="If this flag is used, serapi options are inferred for all"
        " projects.")
    parser.add_argument(
        "--infer-opam-dependencies",
        action="store_true",
        help="If this flag is used, opam dependencies are inferred for all"
        " projects.")
    args = parser.parse_args()
    main(args)
