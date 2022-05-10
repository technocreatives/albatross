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


@click.command(
    help="""Migration tool for GitLab instances

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
    "-t", "--source-token",
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
@click.option("-v", "--verbose", is_flag=True, default=False, help="Verbose output")
@click.option(
    "--debug", is_flag=True, default=False, help="Print debug output. Implies -v"
)
@_prepare_logger
@_call_logger
def main(source_url, source_token, source_group, verbose, debug) -> None:

    logging.info("Opening connection to source")
    source = open_gitlab_connection(url=source_url, token=source_token)

    pprint.pprint(source.groups.get(source_group).__dict__)


# For invocation from the commandline
if __name__ == "__main__":
    main(auto_envvar_prefix="ALBATROSS")
