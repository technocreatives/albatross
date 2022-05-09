# albatross.py

"""
Albatross - A tool for migrating a GitLab.com group/project to a self-hosted instance

Copyright (c) 2022 THETC The Techno Creatives AB
"""

from typing import Any, Callable, Optional
import base64
import click
import gitlab
import logging
import sys


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
            "Call to {} with args {} and kwargs {}".format(func.__name__, args, kwargs)
        )
        return_val = func(*args, **kwargs)
        logging.debug("{} returned with {}".format(func.__name__, return_val))
        return return_val

    return inner


@_call_logger
def open_gitlab_connection(
    url: str, username: Optional[str], pat: Optional[str], token: Optional[str]
) -> gitlab.client.Gitlab:
    url = (
        url
        if url.startswith("http://") or url.startswith("https://")
        else "https://" + url
    )
    logging.debug("URL: {}".format(url))
    token = (
        token
        if token is not None
        else base64.b64encode((username + ":" + pat).encode("utf-8")).decode("utf-8")
    )
    logging.debug("Auth token: {}".format(token))
    return gitlab.Gitlab(url=url, private_token=token)


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
@_prepare_logger
@_call_logger
def main(source_url, source_username, source_pat, source_token, verbose, debug) -> None:
    # Early exit - handcrafted mutual exclusion
    if source_username is None and source_pat is None and source_token is None:
        print(
            "One of username/pat or token must be specified for source", file=sys.stderr
        )
        sys.exit(1)

    logging.info("Opening connection to source")
    source = open_gitlab_connection(
        source_url, source_username, source_pat, source_token
    )


# For invocation from the commandline
if __name__ == "__main__":
    main(auto_envvar_prefix="ALBATROSS")
