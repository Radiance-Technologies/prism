"""
Update math-comp metadata build and install commands.
"""
from pathlib import Path

from prism.project.metadata.storage import MetadataStorage

if __name__ == "__main__":
    module_location = Path(__file__).parent
    mds_file = (module_location.parents[1] / "dataset") / "agg_coq_repos.yml"
    mds = MetadataStorage.load(mds_file)
    new_build_cmd = ["make -C mathcomp all"]
    new_install_cmd = new_build_cmd + ["make -C mathcomp install"]
    new_clean_cmd = ["make -C mathcomp clean"]
    for record in mds.get_all("math-comp", True):
        print(record.build_cmd)
        print(record.install_cmd)
        print(record.clean_cmd)
    mds.update_all(
        "math-comp",
        build_cmd=new_build_cmd,
        install_cmd=new_install_cmd,
        clean_cmd=new_clean_cmd)
    for record in mds.get_all("math-comp", True):
        print(record.build_cmd)
        print(record.install_cmd)
        print(record.clean_cmd)
    MetadataStorage.dump(mds, mds_file)
