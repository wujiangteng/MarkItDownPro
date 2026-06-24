from typing import Literal

import torch


def str2device(device_str: Literal["cpu", "cuda", "mps"]) -> torch.device:
    if device_str == "cpu":
        return torch.device("cpu")
    elif device_str == "cuda":
        return torch.device("cuda")
    elif device_str == "mps":
        return torch.device("mps")
    else:
        raise ValueError(f"Invalid device: {device_str}")


def get_device(device_index: int = None) -> torch.device:
    """
    Automatically detect the best available device for inference.

    Args:
        device_index: The index of GPU device to use if multiple are available.
                      Defaults to None, which uses the first available GPU.

    Returns:
        torch.device: Selected device for model inference.
    """
    if cuda_available():
        return str2device("cuda")
    elif mps_available():
        return str2device("mps")
    else:
        return str2device("cpu")


def cuda_available() -> bool:
    return torch.cuda.is_available()


def mps_available() -> bool:
    return torch.backends.mps.is_available()
