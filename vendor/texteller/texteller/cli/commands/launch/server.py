import numpy as np
import cv2

from starlette.requests import Request
from ray import serve
from ray.serve.handle import DeploymentHandle

from texteller.api import load_model, load_tokenizer, img2latex
from texteller.utils import get_device
from texteller.globals import Globals
from typing import Literal


@serve.deployment(
    num_replicas=Globals().num_replicas,
    ray_actor_options={
        "num_cpus": Globals().ncpu_per_replica,
        "num_gpus": Globals().ngpu_per_replica * 1.0 / 2,
    },
)
class TexTellerServer:
    def __init__(
        self,
        checkpoint_dir: str,
        tokenizer_dir: str,
        use_onnx: bool = False,
        out_format: Literal["latex", "katex"] = "katex",
        keep_style: bool = False,
        num_beams: int = 1,
    ) -> None:
        self.model = load_model(
            model_dir=checkpoint_dir,
            use_onnx=use_onnx,
        )
        self.tokenizer = load_tokenizer(tokenizer_dir=tokenizer_dir)
        self.num_beams = num_beams
        self.out_format = out_format
        self.keep_style = keep_style

        if not use_onnx:
            self.model = self.model.to(get_device())

    def predict(self, image_nparray: np.ndarray) -> str:
        return img2latex(
            model=self.model,
            tokenizer=self.tokenizer,
            images=[image_nparray],
            device=get_device(),
            out_format=self.out_format,
            keep_style=self.keep_style,
            num_beams=self.num_beams,
        )[0]


@serve.deployment()
class Ingress:
    def __init__(self, rec_server: DeploymentHandle) -> None:
        self.texteller_server = rec_server

    async def __call__(self, request: Request) -> str:
        form = await request.form()
        img_rb = await form["img"].read()

        img_nparray = np.frombuffer(img_rb, np.uint8)
        img_nparray = cv2.imdecode(img_nparray, cv2.IMREAD_COLOR)
        img_nparray = cv2.cvtColor(img_nparray, cv2.COLOR_BGR2RGB)

        pred = await self.texteller_server.predict.remote(img_nparray)
        return pred
