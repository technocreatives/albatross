# Albatross

Tool to automate migrating a GitLab group to a GitLab instance

## Usage

```shell
python3 albatross.py -t abcxyz -g 111 -U gitlab.example.com -T 222 -G 0 -O 1
```

The above shows the minimal configuration required to run Albatross, where
- `-t` is a PAT for the source instance. This PAT should have `read_api` access
  (read-only access to all API functions) and the associated user should have Owner
  access of the top-level group to be migrated. Any lesser access leads to undefined
  behaviour.
- `-g` is the group ID on the source instance. All the contents of this group will be
  migrated, including the sub-group structure.
- `-U` is the URL to the destination instance.
- `-T` is a PAT for the destination instance. This PAT should have `api` access (full
  API read-write access) and the associated user should be an Owner of the destination
  group(s) or, optimally, an instance administrator. Keep in mind that all migrated
  issues/comments/merge requests etc. will show this user as the author, so using a
  dedicated service account is recommended.
- `-G` is the group ID for subgroups on the destination instance. This is where
  subgroups from the source group will be recreated. The special value `0` means to put
  subgroups at the instance root.
- `-O` is the group ID for "orphan" projects - projects that sit at the root of the
  source project. Since projects can't sit at the instance root, this must be a valid
  group ID on the destination (and can be the same as `-G`, if it isn't `0`).

There are a few more optional arguments that can be provided:
- `--source-url <URL>` is the URL to the source instance. This defaults to `gitlab.com` if not
  given.
- `--session-cookie <cookie>` is a session cookie on the source instance, belonging to a
  logged in session of the same user as the PAT belongs to. Due to limitations in the
  API, this is required to migrate avatars. Avatars will not be migrated if this is not
  given.
- `--dry-run` runs Albatross without making any changes to the destination side, logging
  the changes that would have been made.
- `--verbose` increases logging. Without this, Albatross is almost completely silent,
  only raising Warnings when something goes wrong.
- `--debug` increases logging WAY more. Be mindful if you pipe the output to a log file;
  this mode logs raw credentials.
- `--sleep-time <seconds>` modifies the number of seconds Albatross pauses every so
  often - after migrating repository content and deleting a destination project. It is 2
  seconds by default.
- `--help` prints the help text.

All command line arguments can also be provided via environment variables with the
prefix `ALBATROSS_`, e.g. `--session-cookie` can be provided via the environment
variable `ALBATROSS_SESSION_COOKIE`.

Albatross is written in Python 3, and has only been tested in 3.9 and 3.10. Your mileage
may vary in other versions.

## Description

This script will recursively migrate all* contents of a GitLab group to a new instance
or group. The following content is migrated:
- Group/subgroup structure
- Projects
- Repositories (including LFS data)
- Issues
- Labels
- Open merge requests
- CI variables (not for archived projects)
- Project milestones (issues are not linked, however)
- Wikis
- Protected tags and branches

The following content is _not_ migrated:
- Users or permissions for projects or groups
- Container, package, or infrastructure registries
- Closed merge requests (due to API limitations)
- Boards
- Group milestones
- CI history
- ... and anything else not enumerated above

Migration starts off with orphan projects (projects at the root of the source group),
then proceeds recursively down each of the sub-groups. Empty groups (groups which
contain no projects or subgroups) are not migrated, nor are empty projects (projects
where the repo is empty; specifically, where it contains no branches).

Albatross uses the local machine as a staging area for repository data, so make sure you
have enough available disk space on the partition containing `/tmp`, especially since
all LFS data will be pulled. The data is removed between projects, so at least not _all_
data needs to be stored at the same time, but still.

Since we know that things can arbitrarily go wrong on the Internet, Albatross creates
and maintains a state file in the same directory as itself. This file records
groups/projects that have already been migrated and, in the case of projects, incomplete
migrations. This means that Albatross can be restarted after an abort/crash and pick up
where it left off. Projects which were incompletely migrated will be deleted on the
destination, then re-migrated.

## License

This project is licensed under either
* Apache License, Version 2.0, ([LICENSE-APACHE](LICENSE-APACHE) or http://www.apache.org/licenses/LICENSE-2.0)
* MIT license ([LICENSE-MIT](LICENSE-MIT) or http://opensource.org/licenses/MIT)

at your option.

## Is it any good?

[yes](https://news.ycombinator.com/item?id=3067434).
