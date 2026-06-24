# Formula image(grayscale) mean and variance
IMAGE_MEAN = 0.9545467
IMAGE_STD = 0.15394445

# Vocabulary size for TexTeller
VOCAB_SIZE = 15000

# Fixed size for input image for TexTeller
FIXED_IMG_SIZE = 448

# Image channel for TexTeller
IMG_CHANNELS = 1  # grayscale image

# Max size of token for embedding
MAX_TOKEN_SIZE = 1024

# Scaling ratio for random resizing when training
MAX_RESIZE_RATIO = 1.15
MIN_RESIZE_RATIO = 0.75

# Minimum height and width for input image for TexTeller
MIN_HEIGHT = 12
MIN_WIDTH = 30

LATEX_DET_MODEL_URL = (
    "https://huggingface.co/TonyLee1256/texteller_det/resolve/main/rtdetr_r50vd_6x_coco.onnx"
)
TEXT_REC_MODEL_URL = (
    "https://huggingface.co/OleehyO/paddleocrv4.onnx/resolve/main/ch_PP-OCRv4_server_rec.onnx"
)
TEXT_DET_MODEL_URL = (
    "https://huggingface.co/OleehyO/paddleocrv4.onnx/resolve/main/ch_PP-OCRv4_det.onnx"
)
