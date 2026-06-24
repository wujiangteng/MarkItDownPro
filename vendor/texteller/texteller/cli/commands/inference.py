"""
CLI command for formula inference from images.
"""

import click

from texteller.api import img2latex, load_model, load_tokenizer


@click.command()
@click.argument("image_path", type=click.Path(exists=True, file_okay=True, dir_okay=False))
@click.option(
    "--model-path",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    default=None,
    help="Path to the model dir path, if not provided, will use model from huggingface repo",
)
@click.option(
    "--tokenizer-path",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    default=None,
    help="Path to the tokenizer dir path, if not provided, will use tokenizer from huggingface repo",
)
@click.option(
    "--output-format",
    type=click.Choice(["latex", "katex"]),
    default="katex",
    help="Output format, either latex or katex",
)
@click.option(
    "--keep-style",
    is_flag=True,
    default=False,
    help="Whether to keep the style of the LaTeX (e.g. bold, italic, etc.)",
)
def inference(image_path, model_path, tokenizer_path, output_format, keep_style):
    """
    CLI command for formula inference from images.
    """
    model = load_model(model_dir=model_path)
    tknz = load_tokenizer(tokenizer_dir=tokenizer_path)

    pred = img2latex(
        model=model,
        tokenizer=tknz,
        images=[image_path],
        out_format=output_format,
        keep_style=keep_style,
    )[0]

    click.echo(f"Predicted LaTeX: ```\n{pred}\n```")
