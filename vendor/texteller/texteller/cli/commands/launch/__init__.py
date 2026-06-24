"""
CLI commands for launching server.
"""

import sys
import time

import click
from ray import serve

from texteller.globals import Globals
from texteller.utils import get_device


@click.command()
@click.option(
    "-ckpt",
    "--checkpoint_dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    default=None,
    help="Path to the checkpoint directory, if not provided, will use model from huggingface repo",
)
@click.option(
    "-tknz",
    "--tokenizer_dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    default=None,
    help="Path to the tokenizer directory, if not provided, will use tokenizer from huggingface repo",
)
@click.option(
    "-p",
    "--port",
    type=int,
    default=8000,
    help="Port to run the server on",
)
@click.option(
    "--num-replicas",
    type=int,
    default=1,
    help="Number of replicas to run the server on",
)
@click.option(
    "--ncpu-per-replica",
    type=float,
    default=1.0,
    help="Number of CPUs per replica",
)
@click.option(
    "--ngpu-per-replica",
    type=float,
    default=1.0,
    help="Number of GPUs per replica",
)
@click.option(
    "--num-beams",
    type=int,
    default=1,
    help="Number of beams to use",
)
@click.option(
    "--use-onnx",
    is_flag=True,
    type=bool,
    default=False,
    help="Use ONNX runtime",
)
def launch(
    checkpoint_dir,
    tokenizer_dir,
    port,
    num_replicas,
    ncpu_per_replica,
    ngpu_per_replica,
    num_beams,
    use_onnx,
):
    """Launch the api server"""
    device = get_device()
    if ngpu_per_replica > 0 and not device.type == "cuda":
        click.echo(
            click.style(
                f"Error: --ngpu-per-replica > 0 but detected device is {device.type}",
                fg="red",
            )
        )
        sys.exit(1)

    Globals().num_replicas = num_replicas
    Globals().ncpu_per_replica = ncpu_per_replica
    Globals().ngpu_per_replica = ngpu_per_replica
    from texteller.cli.commands.launch.server import Ingress, TexTellerServer

    serve.start(http_options={"host": "0.0.0.0", "port": port})
    rec_server = TexTellerServer.bind(
        checkpoint_dir=checkpoint_dir,
        tokenizer_dir=tokenizer_dir,
        use_onnx=use_onnx,
        num_beams=num_beams,
    )
    ingress = Ingress.bind(rec_server)

    serve.run(ingress, route_prefix="/predict")

    while True:
        time.sleep(1)
