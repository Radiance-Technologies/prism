"""
Update math-comp metadata build and install commands.
"""
from pathlib import Path

from prism.project.metadata.storage import MetadataStorage

if __name__ == "__main__":
    module_location = Path(__file__).parent
    mds_file = (module_location.parents[1] / "dataset") / "agg_coq_repos.yml"
    mds = MetadataStorage.load(mds_file)
    new_build_cmd = [
        "make -C mathcomp/algebra",
        "make -C mathcomp/character",
        "make -C mathcomp/field",
        "make -C mathcomp/fingroup",
        "make -C mathcomp/solvable",
        "make -C mathcomp/ssreflect"
    ]
    new_install_cmd = [
        "make -C mathcomp/algebra install",
        "make -C mathcomp/character install",
        "make -C mathcomp/field install",
        "make -C mathcomp/fingroup install",
        "make -C mathcomp/solvable install",
        "make -C mathcomp/ssreflect install"
    ]
    for record in mds.get_all("math-comp", True):
        print(record.build_cmd)
        print(record.install_cmd)
    mds.update_all(
        "math-comp",
        build_cmd=new_build_cmd,
        install_cmd=new_install_cmd)
    for record in mds.get_all("math-comp", True):
        print(record.build_cmd)
        print(record.install_cmd)
    MetadataStorage.dump(mds, mds_file)
