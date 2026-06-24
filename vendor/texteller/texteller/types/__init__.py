from typing import TypeAlias

from optimum.onnxruntime import ORTModelForVision2Seq
from transformers import VisionEncoderDecoderModel

from .bbox import Bbox


TexTellerModel: TypeAlias = VisionEncoderDecoderModel | ORTModelForVision2Seq


__all__ = ["Bbox", "TexTellerModel"]
