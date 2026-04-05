import os
import sys
from typing import Optional, Tuple

import matplotlib
try:
    matplotlib.use("TkAgg")
except Exception:
    matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pydicom
from pydicom.dataset import Dataset
from pydicom.multival import MultiValue


def format_value(value, max_length: int = 50) -> str:
    text = str(value)
    if len(text) > max_length:
        return text[: max_length - 3] + "..."
    return text


def print_dicom_tags(ds: Dataset, max_items: Optional[int] = None) -> None:
    """Affiche un tableau de tous les tags DICOM du dataset."""
    rows = []
    for i, elem in enumerate(ds.iterall()):
        if max_items is not None and i >= max_items:
            break
        tag = f"({elem.tag.group:04X},{elem.tag.element:04X})"
        name = elem.keyword if elem.keyword else elem.name
        vr = elem.VR
        value = format_value(elem.value)
        rows.append((tag, name, vr, value))

    widths = [12, 30, 6, 60]
    header = ["Tag", "Name", "VR", "Value"]
    print("\n" + " | ".join(h.ljust(w) for h, w in zip(header, widths)))
    print("-" * (sum(widths) + 9))
    for tag, name, vr, value in rows:
        print(
            f"{tag.ljust(widths[0])} | {name.ljust(widths[1])} | {vr.ljust(widths[2])} | {value.ljust(widths[3])}"
        )


def get_windowing(ds: Dataset) -> Tuple[Optional[float], Optional[float]]:
    """Lit les valeurs WindowCenter et WindowWidth dans le dataset."""
    wc = ds.get("WindowCenter", None)
    ww = ds.get("WindowWidth", None)
    if isinstance(wc, MultiValue):
        wc = wc[0]
    if isinstance(ww, MultiValue):
        ww = ww[0]
    try:
        wc = float(wc) if wc is not None else None
    except (ValueError, TypeError):
        wc = None
    try:
        ww = float(ww) if ww is not None else None
    except (ValueError, TypeError):
        ww = None
    return wc, ww


def rescale_pixel_array(ds: Dataset, arr: np.ndarray) -> np.ndarray:
    """Applique RescaleSlope et RescaleIntercept si présents."""
    slope = float(ds.get("RescaleSlope", 1.0))
    intercept = float(ds.get("RescaleIntercept", 0.0))
    if slope != 1.0 or intercept != 0.0:
        arr = arr.astype(np.float32) * slope + intercept
    return arr


def apply_window(arr: np.ndarray, center: float, width: float) -> np.ndarray:
    """Fenêtre l'image avec le centre et la largeur donnés."""
    if width <= 0:
        width = 1.0
    low = center - width / 2.0
    high = center + width / 2.0
    arr = np.clip(arr, low, high)
    arr = (arr - low) / (high - low)
    return arr


def show_dicom_image_with_window(ds: Dataset, window_center: Optional[float] = None, window_width: Optional[float] = None) -> None:
    """Affiche l'image DICOM en appliquant le fenêtrage basé sur les métadonnées."""
    if not hasattr(ds, "pixel_array"):
        raise ValueError("Le fichier DICOM ne contient pas de données d'image pixel_array.")

    arr = ds.pixel_array.astype(np.float32)
    arr = rescale_pixel_array(ds, arr)

    if window_center is None or window_width is None:
        metadata_center, metadata_width = get_windowing(ds)
        window_center = metadata_center if window_center is None else window_center
        window_width = metadata_width if window_width is None else window_width

    if window_center is None or window_width is None:
        window_center = np.mean(arr)
        window_width = np.max(arr) - np.min(arr)

    image = apply_window(arr, window_center, window_width)

    if ds.PhotometricInterpretation == "MONOCHROME1":
        image = 1.0 - image

    plt.figure(figsize=(8, 8))
    plt.imshow(image, cmap="gray", aspect="equal")
    plt.axis("off")
    plt.title(
        f"Fenêtrage : centre={window_center:.1f}, largeur={window_width:.1f}"
    )

    backend = plt.get_backend().lower()
    if backend == "agg":
        output_name = os.path.splitext(os.path.basename(ds.filename or "dicom_image"))[0] + "_windowed.png"
        plt.savefig(output_name, bbox_inches="tight", pad_inches=0)
        print(f"Image enregistrée sous : {output_name}")
    else:
        plt.show()


def main(dicom_path: str) -> None:
    if not os.path.exists(dicom_path):
        print(f"Fichier DICOM introuvable : {dicom_path}")
        return

    ds = pydicom.dcmread(dicom_path)
    print(f"Lecture du fichier DICOM : {dicom_path}")
    print(f"Patient : {ds.get('PatientName', 'N/A')}  |  Study Date : {ds.get('StudyDate', 'N/A')}\n")

    print_dicom_tags(ds)

    wc, ww = get_windowing(ds)
    if wc is not None and ww is not None:
        print(f"\nFenêtrage trouvé dans les métadonnées : WindowCenter={wc}, WindowWidth={ww}")
    else:
        print("\nAucun fenêtrage trouvé dans les métadonnées DICOM.")

    show_dicom_image_with_window(ds, wc, ww)


if __name__ == "__main__":
    dicom_file = sys.argv[1] if len(sys.argv) > 1 else "image1.dcm"
    main(dicom_file)
