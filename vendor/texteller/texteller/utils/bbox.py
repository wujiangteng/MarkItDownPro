import heapq
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from texteller.types import Bbox

_MAXV = 999999999


def mask_img(img, bboxes: list[Bbox], bg_color: np.ndarray) -> np.ndarray:
    mask_img = img.copy()
    for bbox in bboxes:
        mask_img[bbox.p.y : bbox.p.y + bbox.h, bbox.p.x : bbox.p.x + bbox.w] = bg_color
    return mask_img


def bbox_merge(sorted_bboxes: list[Bbox]) -> list[Bbox]:
    if len(sorted_bboxes) == 0:
        return []
    bboxes = sorted_bboxes.copy()
    guard = Bbox(_MAXV, bboxes[-1].p.y, -1, -1, label="guard")
    bboxes.append(guard)
    res = []
    prev = bboxes[0]
    for curr in bboxes:
        if prev.ur_point.x <= curr.p.x or not prev.same_row(curr):
            res.append(prev)
            prev = curr
        else:
            prev.w = max(prev.w, curr.ur_point.x - prev.p.x)
    return res


def split_conflict(ocr_bboxes: list[Bbox], latex_bboxes: list[Bbox]) -> list[Bbox]:
    if latex_bboxes == []:
        return ocr_bboxes
    if ocr_bboxes == [] or len(ocr_bboxes) == 1:
        return ocr_bboxes

    bboxes = sorted(ocr_bboxes + latex_bboxes)

    assert len(bboxes) > 1

    heapq.heapify(bboxes)
    res = []
    candidate = heapq.heappop(bboxes)
    curr = heapq.heappop(bboxes)
    idx = 0
    while len(bboxes) > 0:
        idx += 1
        assert candidate.p.x <= curr.p.x or not candidate.same_row(curr)

        if candidate.ur_point.x <= curr.p.x or not candidate.same_row(curr):
            res.append(candidate)
            candidate = curr
            curr = heapq.heappop(bboxes)
        elif candidate.ur_point.x < curr.ur_point.x:
            assert not (candidate.label != "text" and curr.label != "text")
            if candidate.label == "text" and curr.label == "text":
                candidate.w = curr.ur_point.x - candidate.p.x
                curr = heapq.heappop(bboxes)
            elif candidate.label != curr.label:
                if candidate.label == "text":
                    candidate.w = curr.p.x - candidate.p.x
                    res.append(candidate)
                    candidate = curr
                    curr = heapq.heappop(bboxes)
                else:
                    curr.w = curr.ur_point.x - candidate.ur_point.x
                    curr.p.x = candidate.ur_point.x
                    heapq.heappush(bboxes, curr)
                    curr = heapq.heappop(bboxes)

        elif candidate.ur_point.x >= curr.ur_point.x:
            assert not (candidate.label != "text" and curr.label != "text")

            if candidate.label == "text":
                assert curr.label != "text"
                heapq.heappush(
                    bboxes,
                    Bbox(
                        curr.ur_point.x,
                        candidate.p.y,
                        candidate.h,
                        candidate.ur_point.x - curr.ur_point.x,
                        label="text",
                        confidence=candidate.confidence,
                        content=None,
                    ),
                )
                candidate.w = curr.p.x - candidate.p.x
                res.append(candidate)
                candidate = curr
                curr = heapq.heappop(bboxes)
            else:
                assert curr.label == "text"
                curr = heapq.heappop(bboxes)
        else:
            assert False
    res.append(candidate)
    res.append(curr)

    return res


def slice_from_image(img: np.ndarray, ocr_bboxes: list[Bbox]) -> list[np.ndarray]:
    sliced_imgs = []
    for bbox in ocr_bboxes:
        x, y = int(bbox.p.x), int(bbox.p.y)
        w, h = int(bbox.w), int(bbox.h)
        sliced_img = img[y : y + h, x : x + w]
        sliced_imgs.append(sliced_img)
    return sliced_imgs


def draw_bboxes(img: Image.Image, bboxes: list[Bbox], name="annotated_image.png"):
    curr_work_dir = Path(os.getcwd())
    log_dir = curr_work_dir / "logs"
    log_dir.mkdir(exist_ok=True)
    drawer = ImageDraw.Draw(img)
    for bbox in bboxes:
        # Calculate the coordinates for the rectangle to be drawn
        left = bbox.p.x
        top = bbox.p.y
        right = bbox.p.x + bbox.w
        bottom = bbox.p.y + bbox.h

        # Draw the rectangle on the image
        drawer.rectangle([left, top, right, bottom], outline="green", width=1)

        # Optionally, add text label if it exists
        if bbox.label:
            drawer.text((left, top), bbox.label, fill="blue")

        if bbox.content:
            drawer.text((left, bottom - 10), bbox.content[:10], fill="red")

    # Save the image with drawn rectangles
    img.save(log_dir / name)
