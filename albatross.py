# albatross.py

"""
Albatross - A tool for migrating a GitLab.com group/project to a self-hosted instance

Copyright (c) 2022 THETC The Techno Creatives AB
"""

from typing import Any, Callable, Optional
import click
import gitlab
import logging
import pprint


def _prepare_logger(func: Callable) -> Callable:
    """Janky wrapper to prepare the logger before we start invoking it"""

    def inner(*args: tuple, **kwargs: dict) -> Any:
        log_format = "%(asctime)s %(levelname)s   %(message)s"
        date_format = "%Y-%m-%d %H:%M:%S"
        if kwargs["debug"]:
            logging.basicConfig(
                level=logging.DEBUG, format=log_format, datefmt=date_format
            )
        elif kwargs["verbose"]:
            logging.basicConfig(
                level=logging.INFO, format=log_format, datefmt=date_format
            )
        else:
            logging.basicConfig(
                level=logging.WARNING, format=log_format, datefmt=date_format
            )
        logging.debug("Logging started")

        return func(*args, **kwargs)

    return inner


def _call_logger(func: Callable) -> Callable:
    """Janky wrapping call logger, for debugging reasons"""

    def inner(*args: tuple, **kwargs: dict) -> Any:
        logging.debug(
            "CALL to {} with args {} and kwargs {}".format(func.__name__, args, kwargs)
        )
        return_val = func(*args, **kwargs)
        logging.debug("RETURN from {} with {}".format(func.__name__, return_val))
        return return_val

    return inner


@_call_logger
def open_gitlab_connection(url: str, token: Optional[str]) -> gitlab.client.Gitlab:
    url = (
        url
        if url.startswith("http://") or url.startswith("https://")
        else "https://" + url
    )
    logging.debug("URL: {}".format(url))
    gl = gitlab.Gitlab(url=url, private_token=token)
    gl.auth()
    return gl


@_call_logger
def migrate_project(project: Any, dest: Any, dest_gid: int, dry_run: bool) -> None:
    name = project.name
    s_ns = project.namespace.get("full_path")
    d_ns = dest.groups.get(dest_gid).full_path
    logging.info(
        "Migrating project {} from source namespace {} to destination namespace {}".format(
            name, s_ns, d_ns
        )
    )

    if dry_run:
        logging.warning(
            "DRY RUN: project {} will not be created in namespace {}".format(name, d_ns)
        )
    else:
        pass



@_call_logger
def migrate_projects(
    project_list: list[Any],
    dest: Any,
    dest_gid: int,
    dry_run: bool,
) -> None:
    for project in project_list:
        migrate_project(project=project, dest=dest, dest_gid=dest_gid, dry_run=dry_run)
        break


@_call_logger
def migrate(
    source: gitlab.client.Gitlab,
    dest: gitlab.client.Gitlab,
    source_gid: int,
    dest_gid: int,
    orphan_gid: int,
    dry_run: bool,
) -> None:
    logging.debug("Retrieving source group")
    sg = source.groups.get(source_gid)

    logging.debug("Enumerating orphans")
    orphans = sg.projects.list(all=True)
    if len(orphans) == 0:
        logging.info("No orphans to migrate")
    else:
        logging.info("Migrating {} orphans...".format(len(orphans)))
        migrate_projects(
            project_list=orphans,
            dest=dest,
            dest_gid=orphan_gid,
            dry_run=dry_run,
        )

    logging.debug("Enumerating subgroups")
    subgroups = sg.subgroups.list(all=True)
    if len(subgroups) == 0:
        logging.info("No subgroups to migrate")
    else:
        logging.info("Migrating {} subgroups...".format(len(subgroups)))
        raise NotImplementedError("No subgroup handling just yet")


@click.command(
    help="""Migration tool for GitLab instances

The tool requires one group ID on the source side and two on the destination side. For
subgroups on the source side, they can either be recreated as subgroups on the
destination side (given an actual GID) or recreated as groups at the instance root
(given the special GID 0). Projects that live in the group root on the source side -
called "orphan projects" - can't be created at the instance root, so will require an
actual GID on the destination side.

This tool uses the local system as a staging environment when pulling data from the
source and pushing to the target. Make sure you have enough disk space available to
accomodate that.

Any commandline option can also be given via environment variables. i.e. the
"source-url" value can be given via the variable "ALBATROSS_SOURCE_URL".
"""
)
@click.option(
    "--source-url",
    default="gitlab.com",
    help="Instance to read from",
    show_default=True,
)
@click.option(
    "-t",
    "--source-token",
    required=True,
    help="Personal Access Token for the source side",
)
@click.option(
    "-g",
    "--source-group",
    required=True,
    type=int,
    help="Group ID on the source side to migrate from",
)
@click.option("-U", "--dest-url", required=True, help="Instance to write to")
@click.option(
    "-T",
    "--dest-token",
    required=True,
    help="Personal Access Token for the destination side",
)
@click.option(
    "-G",
    "--dest-group",
    required=True,
    type=int,
    help="Group ID on the destination side to migrate subgroups to. 0 means instance root.",
)
@click.option(
    "-O",
    "--dest-orphan-group",
    required=True,
    type=int,
    help="Group ID on the destination side to migrate orphaned projects to. Cannot be 0.",
)
@click.option(
    "-n",
    "--dry-run",
    is_flag=True,
    default=False,
    help="Prevents any write-action on the destination.",
)
@click.option("-v", "--verbose", is_flag=True, default=False, help="Verbose output")
@click.option(
    "--debug", is_flag=True, default=False, help="Print debug output. Implies -v"
)
@_prepare_logger
@_call_logger
def main(
    source_url,
    source_token,
    source_group,
    dest_url,
    dest_token,
    dest_group,
    dest_orphan_group,
    dry_run,
    verbose,
    debug,
) -> None:

    logging.info("Opening connection to source")
    source = open_gitlab_connection(url=source_url, token=source_token)

    logging.info("Opening connection to destination")
    dest = open_gitlab_connection(url=dest_url, token=dest_token)

    logging.info("Starting migration...")
    migrate(
        source=source,
        dest=dest,
        source_gid=source_group,
        dest_gid=dest_group,
        orphan_gid=dest_orphan_group,
        dry_run=dry_run,
    )

    logging.info("Migration complete")


# For invocation from the commandline
if __name__ == "__main__":
    main(auto_envvar_prefix="ALBATROSS")
