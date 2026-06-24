import base64
import io
import os
import re
import shutil
import tempfile

import streamlit as st
from PIL import Image
from streamlit_paste_button import paste_image_button as pbutton

from texteller.api import (
    img2latex,
    load_latexdet_model,
    load_model,
    load_textdet_model,
    load_textrec_model,
    load_tokenizer,
    paragraph2md,
)
from texteller.cli.commands.web.style import (
    HEADER_HTML,
    IMAGE_EMBED_HTML,
    IMAGE_INFO_HTML,
    SUCCESS_GIF_HTML,
)
from texteller.utils import str2device

st.set_page_config(page_title="TexTeller", page_icon="🧮")


@st.cache_resource
def get_texteller(use_onnx):
    return load_model(use_onnx=use_onnx)


@st.cache_resource
def get_tokenizer():
    return load_tokenizer()


@st.cache_resource
def get_latexdet_model():
    return load_latexdet_model()


@st.cache_resource()
def get_textrec_model():
    return load_textrec_model()


@st.cache_resource()
def get_textdet_model():
    return load_textdet_model()


def get_image_base64(img_file):
    buffered = io.BytesIO()
    img_file.seek(0)
    img = Image.open(img_file)
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()


def on_file_upload():
    st.session_state["UPLOADED_FILE_CHANGED"] = True


def change_side_bar():
    st.session_state["CHANGE_SIDEBAR_FLAG"] = True


if "start" not in st.session_state:
    st.session_state["start"] = 1
    st.toast("Hooray!", icon="🎉")

if "UPLOADED_FILE_CHANGED" not in st.session_state:
    st.session_state["UPLOADED_FILE_CHANGED"] = False

if "CHANGE_SIDEBAR_FLAG" not in st.session_state:
    st.session_state["CHANGE_SIDEBAR_FLAG"] = False

if "INF_MODE" not in st.session_state:
    st.session_state["INF_MODE"] = "Formula recognition"


# ====== <sidebar> ======

with st.sidebar:
    num_beams = 1

    st.markdown("# 🔨️ Config")
    st.markdown("")

    inf_mode = st.selectbox(
        "Inference mode",
        ("Formula recognition", "Paragraph recognition"),
        on_change=change_side_bar,
    )

    num_beams = st.number_input(
        "Number of beams", min_value=1, max_value=20, step=1, on_change=change_side_bar
    )

    device = st.radio("device", ("cpu", "cuda", "mps"), on_change=change_side_bar)

    st.markdown("## Seedup")
    use_onnx = st.toggle("ONNX Runtime ")


# ====== </sidebar> ======


# ====== <page> ======

latexrec_model = get_texteller(use_onnx)
tokenizer = get_tokenizer()

if inf_mode == "Paragraph recognition":
    latexdet_model = get_latexdet_model()
    textrec_model = get_textrec_model()
    textdet_model = get_textdet_model()

st.markdown(HEADER_HTML, unsafe_allow_html=True)

uploaded_file = st.file_uploader(" ", type=["jpg", "png"], on_change=on_file_upload)

paste_result = pbutton(
    label="📋 Paste an image",
    background_color="#5BBCFF",
    hover_background_color="#3498db",
)
st.write("")

if st.session_state["CHANGE_SIDEBAR_FLAG"] is True:
    st.session_state["CHANGE_SIDEBAR_FLAG"] = False
elif uploaded_file or paste_result.image_data is not None:
    if st.session_state["UPLOADED_FILE_CHANGED"] is False and paste_result.image_data is not None:
        uploaded_file = io.BytesIO()
        paste_result.image_data.save(uploaded_file, format="PNG")
        uploaded_file.seek(0)

    if st.session_state["UPLOADED_FILE_CHANGED"] is True:
        st.session_state["UPLOADED_FILE_CHANGED"] = False

    img = Image.open(uploaded_file)

    temp_dir = tempfile.mkdtemp()
    png_fpath = os.path.join(temp_dir, "image.png")
    img.save(png_fpath, "PNG")

    with st.container(height=300):
        img_base64 = get_image_base64(uploaded_file)

        st.markdown(
            IMAGE_EMBED_HTML.format(img_base64=img_base64),
            unsafe_allow_html=True,
        )

    st.markdown(
        IMAGE_INFO_HTML.format(img_height=img.height, img_width=img.width),
        unsafe_allow_html=True,
    )

    st.write("")

    with st.spinner("Predicting..."):
        if inf_mode == "Formula recognition":
            pred = img2latex(
                model=latexrec_model,
                tokenizer=tokenizer,
                images=[png_fpath],
                device=str2device(device),
                out_format="katex",
                num_beams=num_beams,
                keep_style=False,
            )[0]
        else:
            pred = paragraph2md(
                img_path=png_fpath,
                latexdet_model=latexdet_model,
                textdet_model=textdet_model,
                textrec_model=textrec_model,
                latexrec_model=latexrec_model,
                tokenizer=tokenizer,
                device=str2device(device),
                num_beams=num_beams,
            )

        st.success("Completed!", icon="✅")
        # st.markdown(SUCCESS_GIF_HTML, unsafe_allow_html=True)
        # st.text_area("Predicted LaTeX", pred, height=150)
        if inf_mode == "Formula recognition":
            st.code(pred, language="latex")
        elif inf_mode == "Paragraph recognition":
            st.code(pred, language="markdown")
        else:
            raise ValueError(f"Invalid inference mode: {inf_mode}")

        if inf_mode == "Formula recognition":
            st.latex(pred)
        elif inf_mode == "Paragraph recognition":
            mixed_res = re.split(r"(\$\$.*?\$\$)", pred, flags=re.DOTALL)
            for text in mixed_res:
                if text.startswith("$$") and text.endswith("$$"):
                    st.latex(text.strip("$$"))
                else:
                    st.markdown(text)

        st.write("")
        st.write("")

        with st.expander(":star2: :gray[Tips for better results]"):
            st.markdown("""
                * :mag_right: Use a clear and high-resolution image.
                * :scissors: Crop images as accurately as possible.
                * :jigsaw: Split large multi line formulas into smaller ones.
                * :page_facing_up: Use images with **white background and black text** as much as possible.
                * :book: Use a font with good readability.
            """)
        shutil.rmtree(temp_dir)

    paste_result.image_data = None

# ====== </page> ======
