import os
import click
from pathlib import Path


@click.command()
def web():
    """Launch the web interface for TexTeller."""
    os.system(f"streamlit run {Path(__file__).parent / 'streamlit_demo.py'}")
