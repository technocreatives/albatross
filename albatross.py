# albatross.py

"""
Albatross - A tool for migrating a GitLab.com group/project to a self-hosted instance

Copyright (c) 2022 THETC The Techno Creatives AB
"""

from base64 import b64encode
from dataclasses import dataclass
from git import Repo
from pprint import pprint as pp
from time import sleep
from typing import Any, Callable, Optional, Tuple
import click
import gitlab
import logging
import math
import os
import requests
import tempfile


@dataclass
class AlbatrossData:
    source: gitlab.client.Gitlab
    dest: gitlab.client.Gitlab
    source_gid: int
    main_gid: int
    orphan_gid: int
    cookie: str
    dry_run: bool
    milestone_map: dict
    sleep_time: int


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
def migrate_avatar(url: str, dest: Any, cookie: str) -> None:
    avatar_req = requests.get(url, cookies={"_gitlab_session": cookie})
    if avatar_req.status_code != 200:
        logging.warning("Failed to retrieve avatar from {}".format(url))
    else:
        dest.avatar = avatar_req.content


@_call_logger
def migrate_variables(source: Any, dest: Any) -> int:
    counter = 0
    for var in source.variables.list():
        logging.debug("Migrating variable {}".format(var.key))
        dest.variables.create(
            {
                "key": var.key,
                "value": var.value,
                "environment_scope": var.environment_scope,
                "masked": var.masked,
                "protected": var.protected,
                "variable_type": var.variable_type,
            }
        )
        counter += 1
    return counter


@_call_logger
def migrate_repo(
    source_url: str, dest_url: str, data: AlbatrossData
) -> Tuple[str, str]:
    @_call_logger
    def dir_size(path):
        size = 0
        for root, _, files in os.walk(path):
            for f in files:
                size += os.stat(os.path.join(root, f)).st_size
        return size

    @_call_logger
    def format_bytes(bts):
        if bts == 0:
            return "0B"
        size_name = ["B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB"]
        i = int(math.floor(math.log(bts, 1024)))
        p = math.pow(1024, i)
        s = round(bts / p, 2)
        return "{}{}".format(s, size_name[i])

    source_auth = b64encode(
        (data.source.user.username + ":" + data.source.private_token).encode("utf-8")
    ).decode("utf-8")
    logging.debug("Derived source auth {}".format(source_auth))
    dest_auth = b64encode(
        (data.dest.user.username + ":" + data.dest.private_token).encode("utf-8")
    ).decode("utf-8")
    logging.debug("Derived dest auth {}".format(dest_auth))
    with tempfile.TemporaryDirectory() as tdir:
        logging.debug("Cloning from {} into {}".format(source_url, tdir))
        repo = Repo.clone_from(
            url=source_url,
            to_path=tdir,
            multi_options=[
                "--config http.extraHeader='Authorization: Basic {}'".format(
                    source_auth
                )
            ],
        )
        git_data = dir_size(tdir)
        logging.debug("Pulling LFS history")
        repo.git.lfs("fetch", "--all")
        lfs_data = dir_size(tdir)
        logging.debug("Adding new remote")
        repo.create_remote(name="final-destination", url=dest_url)
        logging.debug("Adding authorization to repo config")
        repo.git.config(
            "http.extraHeader",
            "Authorization: Basic {}".format(dest_auth),
        )
        logging.debug("Pushing to {}".format(dest_url))
        repo.git.push(
            "final-destination",
            all=True,
            porcelain=True,
        )
    return (format_bytes(git_data), format_bytes(lfs_data - git_data))


@_call_logger
def halt_ci(project: Any) -> int:
    counter = 0
    logging.debug(
        "Halting and destroying all CI jobs for project {}".format(project.name)
    )
    for pipe in project.pipelines.list(as_list=False):
        if pipe.status not in ["success", "failed", "canceled", "skipped"]:
            logging.debug("Destroying pipeline {}".format(pipe.id))
            pipe.delete()
            counter += 1
        else:
            logging.debug("Pipeline {} is not pending; no action taken".format(pipe.id))

    return counter


@_call_logger
def migrate_labels(source: Any, dest: Any) -> int:
    counter = 0
    for label in source.labels.list(as_list=False):
        args = {
            "name": label.name,
            "color": label.color,
        }
        if label.description is not None:
            args["description"] = label.description
        if label.priority is not None:
            args["priority"] = label.priority
        dest.labels.create(args)
        counter += 1
    return counter


@_call_logger
def migrate_protected_branches(source: Any, dest: Any) -> int:
    counter = 0
    pre_protected = dest.protectedbranches.list(all=True)
    for rule in source.protectedbranches.list(as_list=False):
        if any(map(lambda e: e.name == rule.name, pre_protected)):
            continue
        dest.protectedbranches.create(
            {
                "name": rule.name,
                "push_access_level": rule.push_access_levels[0]["access_level"]
                if len(rule.push_access_levels) > 0
                else 0,
                "merge_access_level": rule.merge_access_levels[0]["access_level"]
                if len(rule.merge_access_levels) > 0
                else 0,
                "unprotect_access_level": rule.unprotect_access_levels[0][
                    "access_level"
                ]
                if len(rule.unprotect_access_levels) > 0
                else 0,
                "allow_force_push": rule.allow_force_push,
            }
        )
        counter += 1
    return counter


@_call_logger
def migrate_protected_tags(source: Any, dest: Any) -> int:
    counter = 0
    pre_protected = dest.protectedtags.list(all=True)
    for tag in source.protectedtags.list(as_list=False):
        if any(map(lambda e: e.name == tag.name, pre_protected)):
            continue
        dest.protectedtags.create(
            {
                "name": tag.name,
                "create_access_level": tag.create_access_levels[0]["access_level"]
                if len(tag.create_access_levels) > 0
                else 0,
            }
        )
        counter += 1
    return counter


@_call_logger
def migrate_milestones(
    source: Any, dest: Any, data: AlbatrossData
) -> Tuple[int, AlbatrossData]:
    counter = 0
    for stone in source.milestones.list(as_list=False):
        args = {
            "title": stone.title,
            "description": stone.description,
        }
        if stone.due_date is not None:
            args["due_date"] = stone.due_date
        if stone.start_date is not None:
            args["start_date"] = stone.start_date
        new_stone = dest.milestones.create(args)
        data.milestone_map[stone.id] = new_stone.id
        counter += 1
    return (counter, data)


@_call_logger
def migrate_notes(source: Any, dest: Any) -> int:
    counter = 0
    for note in source.notes.list(as_list=False):
        body = "{}By {}: {}".format(
            "[SYSTEM NOTE] " if note.system else "", note.author["name"], note.body
        )
        dest.notes.create(
            {
                "body": body,
                "confidential": note.confidential,
                "created_at": note.created_at,
            }
        )
        counter += 1
    return counter


@_call_logger
def migrate_merge_requests(
    source: Any, dest: Any, data: AlbatrossData
) -> Tuple[int, int]:
    counter = 0
    n_counter = 0
    for mr in source.mergerequests.list(as_list=False, sort="asc", state="opened"):
        description = "By {}: {}".format(mr.author["name"], mr.description)
        args = {
            "source_branch": mr.source_branch,
            "target_branch": mr.target_branch,
            "title": mr.title,
            "description": description,
            "labels": mr.labels,
        }
        if mr.milestone is not None:
            args["milestone_id"] = data.milestone_map[mr.milestone]
        new_mr = dest.mergerequests.create(args)
        counter += 1
        n_counter += migrate_notes(source=mr, dest=new_mr)
    return (counter, n_counter)


@_call_logger
def migrate_issues(source: Any, dest: Any, data: AlbatrossData) -> Tuple[int, int]:
    counter = 0
    n_counter = 0
    for issue in source.issues.list(as_list=False, sort="asc"):
        description = "By {}: {}".format(issue.author["name"], issue.description)
        args = {
            "title": issue.title,
            "iid": issue.iid,
            "labels": issue.labels,
            "issue_type": issue.issue_type,
            "confidential": issue.confidential,
            "created_at": issue.created_at,
            "description": description,
        }
        if issue.milestone is not None:
            args["milestone_id"] = data.milestone_map[issue.milestone]
        if issue.due_date is not None:
            args["due_date"] = issue.due_date
        d_issue = dest.issues.create(args)
        counter += 1
        n_counter += migrate_notes(source=issue, dest=d_issue)
        if issue.state == "closed":
            d_issue.state_event = "close"
        d_issue.save()
    return (counter, n_counter)


@_call_logger
def migrate_project(project: Any, dest_gid: int, data: AlbatrossData) -> None:
    name = project.name
    s_ns = project.namespace.get("full_path")
    d_ns = data.dest.groups.get(dest_gid).full_path
    logging.info(
        "Migrating project {} from source namespace {} to destination namespace {}".format(
            name, s_ns, d_ns
        )
    )

    if data.dry_run:
        logging.warning(
            "DRY RUN: project {} from namespace {} will not be migrated".format(
                name, s_ns
            )
        )
        return

    logging.debug("Creating project {} in namespace ID {}".format(name, dest_gid))
    d_project = data.dest.projects.create({"name": name, "namespace_id": dest_gid})
    d_project.description = project.description

    if project.avatar_url is not None:
        if data.cookie is not None:
            migrate_avatar(url=project.avatar_url, dest=d_project, cookie=data.cookie)
        else:
            logging.warning(
                "Avatar of project {} in namespace {} will not be migrated due to missing session cookie".format(
                    name, s_ns
                )
            )

    d_project.save()

    num_vars = migrate_variables(source=project, dest=d_project)
    if num_vars > 0:
        logging.info("Migrated {} variables in project {}".format(num_vars, name))

    num_labels = migrate_labels(source=project, dest=d_project)
    if num_labels > 0:
        logging.info("Migrated {} labels in project {}".format(num_labels, name))

    logging.debug("Starting repository migration")
    git, lfs = migrate_repo(
        source_url=project.http_url_to_repo,
        dest_url=d_project.http_url_to_repo,
        data=data,
    )
    logging.info(
        "Migrated {} (plus {} in LFS) repository data in project {}".format(
            git, lfs, name
        )
    )
    logging.debug(
        "Letting the destination breathe for {} seconds".format(data.sleep_time)
    )
    sleep(data.sleep_time)

    num_ptag = migrate_protected_tags(source=project, dest=d_project)
    if num_ptag > 0:
        logging.info("Migrated {} protected tags in project {}".format(num_ptag, name))

    num_pbranch = migrate_protected_branches(source=project, dest=d_project)
    if num_pbranch > 0:
        logging.info(
            "Migrated {} protected branches in project {}".format(num_pbranch, name)
        )

    (num_stones, data) = migrate_milestones(source=project, dest=d_project, data=data)
    if num_stones > 0:
        logging.info("Migrated {} milestones in project {}".format(num_stones, name))

    (num_mrs, num_notes) = migrate_merge_requests(
        source=project, dest=d_project, data=data
    )
    if num_mrs > 0:
        logging.info(
            "Migrated {} open merge requests, containing {} notes, in project {}".format(
                num_mrs, num_notes, name
            )
        )

    (num_issues, num_notes) = migrate_issues(source=project, dest=d_project, data=data)
    if num_issues > 0:
        logging.info(
            "Migrated {} issues, containing {} notes, in project {}".format(
                num_issues, num_notes, name
            )
        )

    # Migrate Wikis

    num_pipes = halt_ci(project=d_project)
    if num_pipes > 0:
        logging.info(
            "Removed {} pending CI pipelines in project {}".format(num_pipes, name)
        )


@_call_logger
def migrate_projects(
    project_list: list[Any], dest_gid: int, data: AlbatrossData
) -> None:
    for project in project_list:
        migrate_project(project=project, dest_gid=dest_gid, data=data)


@_call_logger
def migrate(data: AlbatrossData) -> None:
    logging.debug("Retrieving source group")
    sg = data.source.groups.get(data.source_gid)

    logging.debug("Enumerating orphans")
    orphans = sg.projects.list(all=True)
    if len(orphans) == 0:
        logging.info("No orphans to migrate")
    else:
        logging.info("Migrating {} orphans...".format(len(orphans)))
        migrate_projects(project_list=orphans, dest_gid=data.orphan_gid, data=data)
    logging.info("Finished migrating orphans")

    logging.debug("Enumerating subgroups")
    subgroups = sg.subgroups.list(all=True)
    if len(subgroups) == 0:
        logging.info("No subgroups to migrate")
    else:
        logging.info("Migrating {} subgroups...".format(len(subgroups)))
        raise NotImplementedError("No subgroup handling just yet")
    logging.info("Finished migrating subgroups")


@click.command(
    help="""Migration tool for GitLab instances

This tool migrates:\n
    - Group/subgroup structure\n
    - Projects (including avatar* and description)\n
    - Repositories\n
    - Issues\n
    - Labels\n
    - Open merge requests\n
    - CI variables

This tool does NOT migrate:\n
    - Users and special user permissions\n
    - Containers, packages, or infrastructure\n
    - Boards\n
    - Closed/historic merge requests\n
    - Any CI history

* Avatars are only migrated if a session cookie is provided. Please extract one from a
session belonging to the same user as the source token.

The tool requires one group ID on the source side and two on the destination side. For
subgroups on the source side, they can either be recreated as subgroups on the
destination side (given an actual GID) or recreated as groups at the instance root
(given the special GID 0). Projects that live in the group root on the source side -
called "orphan projects" - can't be created at the instance root, so will require an
actual GID on the destination side. Groups which contain no subgroups or projects will
not be migrated.

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
@click.option(
    "--session-cookie",
    type=str,
    help="Session cookie for the same user as the PAT. If not given, avatars will not be migrated.",
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
@click.option(
    "--sleep-time",
    type=int,
    default=2,
    show_default=True,
    help="Number of seconds to pause after a repository migration to let the destination catch its breath. If you find that branch protection calls fail for no reason, try increasing this.",
)
@_prepare_logger
@_call_logger
def main(
    source_url,
    source_token,
    source_group,
    session_cookie,
    dest_url,
    dest_token,
    dest_group,
    dest_orphan_group,
    dry_run,
    verbose,
    debug,
    sleep_time,
) -> None:

    logging.info("Opening connection to source")
    source = open_gitlab_connection(url=source_url, token=source_token)

    logging.info("Opening connection to destination")
    dest = open_gitlab_connection(url=dest_url, token=dest_token)

    data = AlbatrossData(
        source=source,
        dest=dest,
        source_gid=source_group,
        main_gid=dest_group,
        orphan_gid=dest_orphan_group,
        cookie=session_cookie,
        dry_run=dry_run,
        milestone_map={},
        sleep_time=sleep_time,
    )

    logging.info("Starting migration...")
    migrate(data)

    logging.info("Migration complete")


# For invocation from the commandline
if __name__ == "__main__":
    main(auto_envvar_prefix="ALBATROSS")
