# albatross.py

"""
Albatross - A tool for migrating a GitLab.com group/project to a self-hosted instance

Copyright (c) 2022 THETC The Techno Creatives AB
"""

import click
import gitlab
import logging
import sys
import typing


def _prepare_logger(verbose: bool, debug: bool) -> None:
    log_format = "%(asctime)s %(levelname)s   %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    if debug:
        logging.basicConfig(level=logging.DEBUG, format=log_format, datefmt=date_format)
    elif verbose:
        logging.basicConfig(level=logging.INFO, format=log_format, datefmt=date_format)
    else:
        logging.basicConfig(
            level=logging.WARNING, format=log_format, datefmt=date_format
        )
    logging.debug("Logging started")


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
@click.option("-v", "--verbose", is_flag=True, default=False, help="Verbose output")
@click.option(
    "--debug", is_flag=True, default=False, help="Print debug output. Implies -v"
)
def main(source_url, source_username, source_pat, source_token, verbose, debug) -> None:
    # Early exit - handcrafted mutual exclusion
    if source_username is None and source_pat is None and source_token is None:
        print(
            "One of username/pat or token must be specified for source", file=sys.stderr
        )
        sys.exit(1)

    # Create the logger
    _prepare_logger(verbose, debug)


# For invocation from the commandline
if __name__ == "__main__":
    main(auto_envvar_prefix="ALBATROSS")
