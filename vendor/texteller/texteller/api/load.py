from pathlib import Path

import wget
from onnxruntime import InferenceSession
from transformers import RobertaTokenizerFast

from texteller.constants import LATEX_DET_MODEL_URL, TEXT_DET_MODEL_URL, TEXT_REC_MODEL_URL
from texteller.globals import Globals
from texteller.logger import get_logger
from texteller.models import TexTeller
from texteller.paddleocr import predict_det, predict_rec
from texteller.paddleocr.utility import parse_args
from texteller.utils import cuda_available, mkdir, resolve_path
from texteller.types import TexTellerModel

_logger = get_logger(__name__)


def load_model(model_dir: str | None = None, use_onnx: bool = False) -> TexTellerModel:
    """
    Load the TexTeller model for LaTeX recognition.

    This function loads the main TexTeller model, which is responsible for
    converting images to LaTeX. It can load either the standard PyTorch model
    or the optimized ONNX version.

    Args:
        model_dir: Directory containing the model files. If None, uses the default model.
        use_onnx: Whether to load the ONNX version of the model for faster inference.
                  Requires the 'optimum' package and ONNX Runtime.

    Returns:
        Loaded TexTeller model instance

    Example:
        >>> from texteller import load_model
        >>>
        >>> model = load_model(use_onnx=True)
    """
    return TexTeller.from_pretrained(model_dir, use_onnx=use_onnx)


def load_tokenizer(tokenizer_dir: str | None = None) -> RobertaTokenizerFast:
    """
    Load the tokenizer for the TexTeller model.

    This function loads the tokenizer used by the TexTeller model for
    encoding and decoding LaTeX sequences.

    Args:
        tokenizer_dir: Directory containing the tokenizer files. If None, uses the default tokenizer.

    Returns:
        RobertaTokenizerFast instance

    Example:
        >>> from texteller import load_tokenizer
        >>>
        >>> tokenizer = load_tokenizer()
    """
    return TexTeller.get_tokenizer(tokenizer_dir)


def load_latexdet_model() -> InferenceSession:
    """
    Load the LaTeX detection model.

    This function loads the model responsible for detecting LaTeX formulas in images.
    The model is implemented as an ONNX InferenceSession for optimal performance.

    Returns:
        ONNX InferenceSession for LaTeX detection

    Example:
        >>> from texteller import load_latexdet_model
        >>>
        >>> detector = load_latexdet_model()
    """
    fpath = _maybe_download(LATEX_DET_MODEL_URL)
    return InferenceSession(
        resolve_path(fpath),
        providers=["CUDAExecutionProvider" if cuda_available() else "CPUExecutionProvider"],
    )


def load_textrec_model() -> predict_rec.TextRecognizer:
    """
    Load the text recognition model.

    This function loads the model responsible for recognizing regular text in images.
    It's based on PaddleOCR's text recognition model.

    Returns:
        PaddleOCR TextRecognizer instance

    Example:
        >>> from texteller import load_textrec_model
        >>>
        >>> text_recognizer = load_textrec_model()
    """
    fpath = _maybe_download(TEXT_REC_MODEL_URL)
    paddleocr_args = parse_args()
    paddleocr_args.use_onnx = True
    paddleocr_args.rec_model_dir = resolve_path(fpath)
    paddleocr_args.use_gpu = cuda_available()
    predictor = predict_rec.TextRecognizer(paddleocr_args)
    return predictor


def load_textdet_model() -> predict_det.TextDetector:
    """
    Load the text detection model.

    This function loads the model responsible for detecting text regions in images.
    It's based on PaddleOCR's text detection model.

    Returns:
        PaddleOCR TextDetector instance

    Example:
        >>> from texteller import load_textdet_model
        >>>
        >>> text_detector = load_textdet_model()
    """
    fpath = _maybe_download(TEXT_DET_MODEL_URL)
    paddleocr_args = parse_args()
    paddleocr_args.use_onnx = True
    paddleocr_args.det_model_dir = resolve_path(fpath)
    paddleocr_args.use_gpu = cuda_available()
    predictor = predict_det.TextDetector(paddleocr_args)
    return predictor


def _maybe_download(url: str, dirpath: str | None = None, force: bool = False) -> Path:
    """
    Download a file if it doesn't already exist.

    Args:
        url: URL to download from
        dirpath: Directory to save the file in. If None, uses the default cache directory.
        force: Whether to force download even if the file already exists

    Returns:
        Path to the downloaded file
    """
    if dirpath is None:
        dirpath = Globals().cache_dir
    mkdir(dirpath)

    fname = Path(url).name
    fpath = Path(dirpath) / fname
    if not fpath.exists() or force:
        _logger.info(f"Downloading {fname} from {url} to {fpath}")
        wget.download(url, resolve_path(fpath))

    return fpath
