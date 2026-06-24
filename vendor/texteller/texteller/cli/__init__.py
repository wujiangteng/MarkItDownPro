"""
CLI entry point for TexTeller.
"""

import time

import click

from texteller.cli.commands.inference import inference
from texteller.cli.commands.launch import launch
from texteller.cli.commands.web import web


@click.group()
def cli():
    pass


cli.add_command(inference)
cli.add_command(web)
cli.add_command(launch)


if __name__ == "__main__":
    cli()
