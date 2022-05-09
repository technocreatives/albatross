# albatross.py

"""
Albatross - A tool for migrating a GitLab.com group/project to a self-hosted instance

Copyright (c) 2022 THETC The Techno Creatives AB
"""

import click
import gitlab
import sys
import typing


@click.command(
    help="""Migration tool for GitLab instances

For both the source and target instances a username and PAT OR an (RFC 7235) auth token
must be defined. If both are defined, then the token takes precedence.

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
@click.option("--source-username", help="Username on the source side")
@click.option("--source-pat", help="Personal Access Token on the source side")
@click.option("--source-token", help="HTTP Auth token for the source side")
def main(source_url, source_username, source_pat, source_token) -> None:
    # Early exit - handcrafted mutual exclusion
    if source_username is None and source_pat is None and source_token is None:
        print(
            "One of username/pat or token must be specified for source", file=sys.stderr
        )
        sys.exit(1)


# For invocation from the commandline
if __name__ == "__main__":
    main(auto_envvar_prefix="ALBATROSS")
