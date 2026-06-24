from pathlib import Path

from transformers import RobertaTokenizerFast, VisionEncoderDecoderConfig, VisionEncoderDecoderModel

from texteller.constants import (
    FIXED_IMG_SIZE,
    IMG_CHANNELS,
    MAX_TOKEN_SIZE,
    VOCAB_SIZE,
)
from texteller.globals import Globals
from texteller.types import TexTellerModel
from texteller.utils import cuda_available


class TexTeller(VisionEncoderDecoderModel):
    def __init__(self):
        config = VisionEncoderDecoderConfig.from_pretrained(Globals().repo_name)
        config.encoder.image_size = FIXED_IMG_SIZE
        config.encoder.num_channels = IMG_CHANNELS
        config.decoder.vocab_size = VOCAB_SIZE
        config.decoder.max_position_embeddings = MAX_TOKEN_SIZE

        super().__init__(config=config)

    @classmethod
    def from_pretrained(cls, model_dir: str | None = None, use_onnx=False) -> TexTellerModel:
        if model_dir is None or model_dir == Globals().repo_name:
            if not use_onnx:
                return VisionEncoderDecoderModel.from_pretrained(Globals().repo_name)
            else:
                from optimum.onnxruntime import ORTModelForVision2Seq

                return ORTModelForVision2Seq.from_pretrained(
                    Globals().repo_name,
                    provider="CUDAExecutionProvider"
                    if cuda_available()
                    else "CPUExecutionProvider",
                )
        model_dir = Path(model_dir).resolve()
        return VisionEncoderDecoderModel.from_pretrained(str(model_dir))

    @classmethod
    def get_tokenizer(cls, tokenizer_dir: str = None) -> RobertaTokenizerFast:
        if tokenizer_dir is None or tokenizer_dir == Globals().repo_name:
            return RobertaTokenizerFast.from_pretrained(Globals().repo_name)
        tokenizer_dir = Path(tokenizer_dir).resolve()
        return RobertaTokenizerFast.from_pretrained(str(tokenizer_dir))
