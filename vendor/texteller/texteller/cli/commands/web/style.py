from texteller.utils import lines_dedent


HEADER_HTML = lines_dedent("""
    <h1 style="color: black; text-align: center;">
        <img src="https://raw.githubusercontent.com/OleehyO/TexTeller/main/assets/fire.svg" width="100">
        𝚃𝚎𝚡𝚃𝚎𝚕𝚕𝚎𝚛
        <img src="https://raw.githubusercontent.com/OleehyO/TexTeller/main/assets/fire.svg" width="100">
    </h1>
    """)

SUCCESS_GIF_HTML = lines_dedent("""
    <h1 style="color: black; text-align: center;">
        <img src="https://slackmojis.com/emojis/90621-clapclap-e/download" width="50">
        <img src="https://slackmojis.com/emojis/90621-clapclap-e/download" width="50">
        <img src="https://slackmojis.com/emojis/90621-clapclap-e/download" width="50">
    </h1>
    """)

FAIL_GIF_HTML = lines_dedent("""
    <h1 style="color: black; text-align: center;">
        <img src="https://slackmojis.com/emojis/51439-allthethings_intensifies/download">
        <img src="https://slackmojis.com/emojis/51439-allthethings_intensifies/download">
        <img src="https://slackmojis.com/emojis/51439-allthethings_intensifies/download">
    </h1>
    """)

IMAGE_EMBED_HTML = lines_dedent("""
    <style>
    .centered-container {{
        text-align: center;
    }}
    .centered-image {{
        display: block;
        margin-left: auto;
        margin-right: auto;
        max-height: 350px;
        max-width: 100%;
    }}
    </style>
    <div class="centered-container">
        <img src="data:image/png;base64,{img_base64}" class="centered-image" alt="Input image">
    </div>
    """)

IMAGE_INFO_HTML = lines_dedent("""
    <style>
    .centered-container {{
        text-align: center;
    }}
    </style>
    <div class="centered-container">
        <p style="color:gray;">Input image ({img_height}✖️{img_width})</p>
    </div>
    """)
