import re
import time
from collections import Counter
from typing import Literal

import cv2
import numpy as np
import torch
from onnxruntime import InferenceSession
from optimum.onnxruntime import ORTModelForVision2Seq
from transformers import GenerationConfig, RobertaTokenizerFast

from texteller.constants import MAX_TOKEN_SIZE
from texteller.logger import get_logger
from texteller.paddleocr import predict_det, predict_rec
from texteller.types import Bbox, TexTellerModel
from texteller.utils import (
    bbox_merge,
    get_device,
    mask_img,
    readimgs,
    remove_style,
    slice_from_image,
    split_conflict,
    transform,
    add_newlines,
)

from .detection import latex_detect
from .format import format_latex
from .katex import to_katex

_logger = get_logger()


def img2latex(
    model: TexTellerModel,
    tokenizer: RobertaTokenizerFast,
    images: list[str] | list[np.ndarray],
    device: torch.device | None = None,
    out_format: Literal["latex", "katex"] = "latex",
    keep_style: bool = False,
    max_tokens: int = MAX_TOKEN_SIZE,
    num_beams: int = 1,
    no_repeat_ngram_size: int = 0,
) -> list[str]:
    """
    Convert images to LaTeX or KaTeX formatted strings.

    Args:
        model: The TexTeller or ORTModelForVision2Seq model instance
        tokenizer: The tokenizer for the model
        images: List of image paths or numpy arrays (RGB format)
        device: The torch device to use (defaults to available GPU or CPU)
        out_format: Output format, either "latex" or "katex"
        keep_style: Whether to keep the style of the LaTeX
        max_tokens: Maximum number of tokens to generate
        num_beams: Number of beams for beam search
        no_repeat_ngram_size: Size of n-grams to prevent repetition

    Returns:
        List of LaTeX or KaTeX strings corresponding to each input image

    Example:
        >>> import torch
        >>> from texteller import load_model, load_tokenizer, img2latex
        >>>
        >>> model = load_model(model_path=None, use_onnx=False)
        >>> tokenizer = load_tokenizer(tokenizer_path=None)
        >>> device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        >>>
        >>> res = img2latex(model, tokenizer, ["path/to/image.png"], device=device, out_format="katex")
    """
    assert isinstance(images, list)
    assert len(images) > 0

    if device is None:
        device = get_device()

    if device.type != model.device.type:
        if isinstance(model, ORTModelForVision2Seq):
            _logger.warning(
                f"Onnxruntime device mismatch: detected {str(device)} but model is on {str(model.device)}, using {str(model.device)} instead"
            )
        else:
            model = model.to(device=device)

    if isinstance(images[0], str):
        images = readimgs(images)
    else:  # already numpy array(rgb format)
        assert isinstance(images[0], np.ndarray)
        images = images

    images = transform(images)
    pixel_values = torch.stack(images)

    generate_config = GenerationConfig(
        max_new_tokens=max_tokens,
        num_beams=num_beams,
        do_sample=False,
        pad_token_id=tokenizer.pad_token_id,
        eos_token_id=tokenizer.eos_token_id,
        bos_token_id=tokenizer.bos_token_id,
        no_repeat_ngram_size=no_repeat_ngram_size,
    )
    pred = model.generate(
        pixel_values.to(model.device),
        generation_config=generate_config,
    )

    res = tokenizer.batch_decode(pred, skip_special_tokens=True)

    if out_format == "katex":
        res = [to_katex(r) for r in res]

    if not keep_style:
        res = [remove_style(r) for r in res]

    res = [format_latex(r) for r in res]
    res = [add_newlines(r) for r in res]
    return res


def paragraph2md(
    img_path: str,
    latexdet_model: InferenceSession,
    textdet_model: predict_det.TextDetector,
    textrec_model: predict_rec.TextRecognizer,
    latexrec_model: TexTellerModel,
    tokenizer: RobertaTokenizerFast,
    device: torch.device | None = None,
    num_beams=1,
) -> str:
    """
    Convert an image containing both text and mathematical formulas to markdown format.

    This function processes a mixed-content image by:
    1. Detecting mathematical formulas using a latex detection model
    2. Masking detected formula areas and detecting text regions using OCR
    3. Recognizing text in the detected regions
    4. Converting formula regions to LaTeX using the latex recognition model
    5. Combining all detected elements into a properly formatted markdown string

    Args:
        img_path: Path to the input image containing text and formulas
        latexdet_model: ONNX InferenceSession for LaTeX formula detection
        textdet_model: OCR text detector model
        textrec_model: OCR text recognition model
        latexrec_model: TexTeller model for LaTeX formula recognition
        tokenizer: Tokenizer for the LaTeX recognition model
        device: The torch device to use (defaults to available GPU or CPU)
        num_beams: Number of beams for beam search during LaTeX generation

    Returns:
        Markdown formatted string containing the recognized text and formulas

    Example:
        >>> from texteller import load_latexdet_model, load_textdet_model, load_textrec_model, load_tokenizer, paragraph2md
        >>>
        >>> # Load all required models
        >>> latexdet_model = load_latexdet_model()
        >>> textdet_model = load_textdet_model()
        >>> textrec_model = load_textrec_model()
        >>> latexrec_model = load_model()
        >>> tokenizer = load_tokenizer()
        >>>
        >>> # Convert image to markdown
        >>> markdown_text = paragraph2md(
        ...     img_path="path/to/mixed_content_image.jpg",
        ...     latexdet_model=latexdet_model,
        ...     textdet_model=textdet_model,
        ...     textrec_model=textrec_model,
        ...     latexrec_model=latexrec_model,
        ...     tokenizer=tokenizer,
        ... )
    """
    img = cv2.imread(img_path)
    corners = [tuple(img[0, 0]), tuple(img[0, -1]), tuple(img[-1, 0]), tuple(img[-1, -1])]
    bg_color = np.array(Counter(corners).most_common(1)[0][0])

    start_time = time.time()
    latex_bboxes = latex_detect(img_path, latexdet_model)
    end_time = time.time()
    _logger.info(f"latex_det_model time: {end_time - start_time:.2f}s")
    latex_bboxes = sorted(latex_bboxes)
    latex_bboxes = bbox_merge(latex_bboxes)
    masked_img = mask_img(img, latex_bboxes, bg_color)

    start_time = time.time()
    det_prediction, _ = textdet_model(masked_img)
    end_time = time.time()
    _logger.info(f"ocr_det_model time: {end_time - start_time:.2f}s")
    ocr_bboxes = [
        Bbox(
            p[0][0],
            p[0][1],
            p[3][1] - p[0][1],
            p[1][0] - p[0][0],
            label="text",
            confidence=None,
            content=None,
        )
        for p in det_prediction
    ]

    ocr_bboxes = sorted(ocr_bboxes)
    ocr_bboxes = bbox_merge(ocr_bboxes)
    ocr_bboxes = split_conflict(ocr_bboxes, latex_bboxes)
    ocr_bboxes = list(filter(lambda x: x.label == "text", ocr_bboxes))

    sliced_imgs: list[np.ndarray] = slice_from_image(img, ocr_bboxes)
    start_time = time.time()
    rec_predictions, _ = textrec_model(sliced_imgs)
    end_time = time.time()
    _logger.info(f"ocr_rec_model time: {end_time - start_time:.2f}s")

    assert len(rec_predictions) == len(ocr_bboxes)
    for content, bbox in zip(rec_predictions, ocr_bboxes):
        bbox.content = content[0]

    latex_imgs = []
    for bbox in latex_bboxes:
        latex_imgs.append(img[bbox.p.y : bbox.p.y + bbox.h, bbox.p.x : bbox.p.x + bbox.w])
    start_time = time.time()
    latex_rec_res = img2latex(
        model=latexrec_model,
        tokenizer=tokenizer,
        images=latex_imgs,
        num_beams=num_beams,
        out_format="katex",
        device=device,
        keep_style=False,
    )
    end_time = time.time()
    _logger.info(f"latex_rec_model time: {end_time - start_time:.2f}s")

    for bbox, content in zip(latex_bboxes, latex_rec_res):
        if bbox.label == "embedding":
            bbox.content = " $" + content + "$ "
        elif bbox.label == "isolated":
            bbox.content = "\n\n" + r"$$" + content + r"$$" + "\n\n"

    bboxes = sorted(ocr_bboxes + latex_bboxes)
    if bboxes == []:
        return ""

    md = ""
    prev = Bbox(bboxes[0].p.x, bboxes[0].p.y, -1, -1, label="guard")
    for curr in bboxes:
        # Add the formula number back to the isolated formula
        if prev.label == "isolated" and curr.label == "text" and prev.same_row(curr):
            curr.content = curr.content.strip()
            if curr.content.startswith("(") and curr.content.endswith(")"):
                curr.content = curr.content[1:-1]

            if re.search(r"\\tag\{.*\}$", md[:-4]) is not None:
                # in case of multiple tag
                md = md[:-5] + f", {curr.content}" + "}" + md[-4:]
            else:
                md = md[:-4] + f"\\tag{{{curr.content}}}" + md[-4:]
            continue

        if not prev.same_row(curr):
            md += " "

        if curr.label == "embedding":
            # remove the bold effect from inline formulas
            curr.content = remove_style(curr.content)

            # change split environment into aligned
            curr.content = curr.content.replace(r"\begin{split}", r"\begin{aligned}")
            curr.content = curr.content.replace(r"\end{split}", r"\end{aligned}")

            # remove extra spaces (keeping only one)
            curr.content = re.sub(r" +", " ", curr.content)
            assert curr.content.startswith("$") and curr.content.endswith("$")
            curr.content = " $" + curr.content.strip("$") + "$ "
        md += curr.content
        prev = curr

    return md.strip()
