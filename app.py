import base64
import os
import re
import uuid
from datetime import datetime
from io import BytesIO
from typing import Dict, Optional, Tuple

import numpy as np
import pydicom
from flask import Flask, flash, get_flashed_messages, redirect, render_template, request, session, url_for
from PIL import Image
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"dcm", "dicom"}
MAX_CONTENT_LENGTH = 50 * 1024 * 1024
MAX_SESSION_BYTES = 2 * 1024 * 1024 * 1024
SESSION_UPLOADS_KEY = "session_uploads"

app = Flask(__name__)
app.secret_key = "change-this-secret"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename: str) -> bool:
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return extension in ALLOWED_EXTENSIONS


def get_session_uploads() -> list:
    return session.get(SESSION_UPLOADS_KEY, [])


def get_session_total_bytes() -> int:
    return sum(item.get("size", 0) for item in get_session_uploads())


def add_upload_to_session(file_id: str, filename: str, size: int) -> None:
    uploads = get_session_uploads()
    uploads.append(
        {
            "file_id": file_id,
            "filename": filename,
            "size": size,
            "uploaded_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    session[SESSION_UPLOADS_KEY] = uploads


def normalize_tag_query(query: str) -> str:
    return query.strip().lower()


def get_windowing(ds: pydicom.dataset.Dataset) -> Tuple[Optional[float], Optional[float]]:
    wc = ds.get("WindowCenter", None)
    ww = ds.get("WindowWidth", None)
    if isinstance(wc, pydicom.multival.MultiValue):
        wc = wc[0]
    if isinstance(ww, pydicom.multival.MultiValue):
        ww = ww[0]
    try:
        wc = float(wc) if wc is not None else None
    except (TypeError, ValueError):
        wc = None
    try:
        ww = float(ww) if ww is not None else None
    except (TypeError, ValueError):
        ww = None
    return wc, ww


def rescale_pixel_array(ds: pydicom.dataset.Dataset, arr: np.ndarray) -> np.ndarray:
    slope = float(ds.get("RescaleSlope", 1.0))
    intercept = float(ds.get("RescaleIntercept", 0.0))
    if slope != 1.0 or intercept != 0.0:
        arr = arr.astype(np.float32) * slope + intercept
    return arr


def apply_window(arr: np.ndarray, center: float, width: float) -> np.ndarray:
    if width <= 0:
        width = 1.0
    low = center - width / 2.0
    high = center + width / 2.0
    arr = np.clip(arr, low, high)
    arr = (arr - low) / max(high - low, 1.0)
    return arr


def dicom_to_base64(ds: pydicom.dataset.Dataset, center: float, width: float) -> str:
    pixel_array = ds.pixel_array.astype(np.float32)
    pixel_array = rescale_pixel_array(ds, pixel_array)
    pixel_array = apply_window(pixel_array, center, width)
    if getattr(ds, "PhotometricInterpretation", "MONOCHROME2") == "MONOCHROME1":
        pixel_array = 1.0 - pixel_array
    image = Image.fromarray((pixel_array * 255).astype(np.uint8))
    buffered = BytesIO()
    image.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("ascii")


def dicom_to_thumbnail(ds: pydicom.dataset.Dataset) -> str:
    pixel_array = ds.pixel_array.astype(np.float32)
    pixel_array = rescale_pixel_array(ds, pixel_array)
    # Use default windowing for thumbnail
    wc, ww = get_windowing(ds)
    if wc is None or ww is None:
        wc = float(np.mean(pixel_array))
        ww = float(np.max(pixel_array) - np.min(pixel_array))
    pixel_array = apply_window(pixel_array, wc, ww)
    if getattr(ds, "PhotometricInterpretation", "MONOCHROME2") == "MONOCHROME1":
        pixel_array = 1.0 - pixel_array
    image = Image.fromarray((pixel_array * 255).astype(np.uint8))
    # Resize to thumbnail
    image = image.resize((256, 256), Image.LANCZOS)
    buffered = BytesIO()
    image.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("ascii")


def format_dicom_value(value) -> str:
    if isinstance(value, (list, tuple, pydicom.multival.MultiValue)):
        return ", ".join(str(v) for v in value) if value else ""
    return str(value)


def build_tag_table(ds: pydicom.dataset.Dataset) -> list[Dict[str, str]]:
    rows = []
    for elem in ds.iterall():
        rows.append(
            {
                "tag": f"({elem.tag.group:04X},{elem.tag.element:04X})",
                "name": elem.keyword or elem.name,
                "vr": elem.VR,
                "value": format_dicom_value(elem.value),
            }
        )
    return rows


def find_tag_value(ds: pydicom.dataset.Dataset, query: str) -> Optional[str]:
    normalized = normalize_tag_query(query)
    if not normalized:
        return None

    tag_pattern = re.compile(r"^\(?([0-9a-fA-F]{4})\s*,\s*([0-9a-fA-F]{4})\)?$")
    match = tag_pattern.match(query.strip())
    if match:
        group = int(match.group(1), 16)
        element = int(match.group(2), 16)
        tag = pydicom.tag.Tag(group, element)
        if tag in ds:
            return format_dicom_value(ds[tag].value)
        return None

    query_lower = normalized
    for elem in ds.iterall():
        name = (elem.keyword or elem.name or "").lower()
        if query_lower == name or query_lower in name:
            return format_dicom_value(elem.value)
    return None


def get_uploaded_file_path(file_id: str) -> str:
    return os.path.join(app.config["UPLOAD_FOLDER"], f"{secure_filename(file_id)}.dcm")

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        if "dicom_file" not in request.files:
            flash("Aucun fichier sélectionné.")
            return redirect(url_for("index"))
        file = request.files["dicom_file"]
        if file.filename == "":
            flash("Aucun fichier sélectionné.")
            return redirect(url_for("index"))
        if file and allowed_file(file.filename):
            file_size = len(file.read())
            file.seek(0)
            if get_session_total_bytes() + file_size > MAX_SESSION_BYTES:
                flash("Limite de session atteinte : supprimez des fichiers ou rafraichissez la page.")
                return redirect(url_for("index"))

            file_id = str(uuid.uuid4())
            path = get_uploaded_file_path(file_id)
            file.save(path)
            add_upload_to_session(file_id, file.filename, file_size)
            return redirect(url_for("view_dicom", file_id=file_id))
        flash("Format non autorisé. Utilisez un fichier DICOM (.dcm ou .dicom).")
        return redirect(url_for("index"))

    session_uploads = get_session_uploads()
    session_total_mb = round(get_session_total_bytes() / (1024 * 1024), 1)
    session_limit_gb = round(MAX_SESSION_BYTES / (1024 * 1024 * 1024), 1)
    return render_template(
        "index.html",
        session_uploads=session_uploads,
        session_total_mb=session_total_mb,
        session_limit_gb=session_limit_gb,
        session_upload_count=len(session_uploads),
    )

@app.route("/clear_session", methods=["POST"])
def clear_session():
    session.pop(SESSION_UPLOADS_KEY, None)
    flash("Session réinitialisée avec succès.")
    return redirect(url_for("index"))

@app.route("/view/<file_id>", methods=["GET"])
def view_dicom(file_id: str):
    path = get_uploaded_file_path(file_id)
    if not os.path.exists(path):
        flash("Fichier DICOM introuvable ou expiré.")
        return redirect(url_for("index"))

    ds = pydicom.dcmread(path)
    wc_default, ww_default = get_windowing(ds)
    if wc_default is None or ww_default is None:
        wc_default = float(np.mean(ds.pixel_array))
        ww_default = float(np.max(ds.pixel_array) - np.min(ds.pixel_array))

    wc = request.args.get("window_center", str(wc_default))
    ww = request.args.get("window_width", str(ww_default))
    tag_query = request.args.get("tag_query", "")

    try:
        window_center = float(wc)
    except ValueError:
        window_center = wc_default
    try:
        window_width = float(ww)
    except ValueError:
        window_width = ww_default

    image_data = dicom_to_base64(ds, window_center, window_width)
    tag_value = find_tag_value(ds, tag_query) if tag_query.strip() else None
    if tag_query and tag_value is None:
        flash(f"Tag non trouvé pour '{tag_query}'.")

    tags = build_tag_table(ds)
    # Extract summary metadata
    modality = ds.get("Modality", "N/A")
    patient_id = ds.get("PatientID", "N/A")
    slice_count = 1  # For single DICOM file
    encryption = "None"  # DICOM doesn't typically have encryption info
    study_instance_uid = ds.get("StudyInstanceUID", "N/A")
    
    # Additional metadata for image viewer
    patient_birth_date = ds.get("PatientBirthDate", "N/A")
    study_description = ds.get("StudyDescription", "N/A")
    acquisition_date_time = ds.get("AcquisitionDateTime", ds.get("StudyDate", "N/A"))
    institution_name = ds.get("InstitutionName", "N/A")
    zoom = 100  # Default zoom
    
    return render_template(
        "view.html",
        file_id=file_id,
        patient_name=ds.get("PatientName", "N/A"),
        study_date=ds.get("StudyDate", "N/A"),
        image_data=image_data,
        window_center=window_center,
        window_width=window_width,
        default_window_center=wc_default,
        default_window_width=ww_default,
        tag_query=tag_query,
        tag_value=tag_value,
        tags=tags,
        modality=modality,
        patient_id=patient_id,
        slice_count=slice_count,
        encryption=encryption,
        study_instance_uid=study_instance_uid,
        patient_birth_date=patient_birth_date,
        study_description=study_description,
        acquisition_date_time=acquisition_date_time,
        institution_name=institution_name,
        zoom=zoom,
    )

@app.route("/image_data/<file_id>", methods=["GET"])
def image_data_endpoint(file_id: str):
    path = get_uploaded_file_path(file_id)
    if not os.path.exists(path):
        return {"error": "File not found"}, 404

    ds = pydicom.dcmread(path)
    wc_default, ww_default = get_windowing(ds)
    if wc_default is None or ww_default is None:
        wc_default = float(np.mean(ds.pixel_array))
        ww_default = float(np.max(ds.pixel_array) - np.min(ds.pixel_array))

    wc = request.args.get("wc", str(wc_default))
    ww = request.args.get("ww", str(ww_default))

    try:
        window_center = float(wc)
    except ValueError:
        window_center = wc_default
    try:
        window_width = float(ww)
    except ValueError:
        window_width = ww_default

    image_data = dicom_to_base64(ds, window_center, window_width)
    return {"image_data": image_data}

@app.route("/image/<file_id>", methods=["GET"])
def image_view(file_id: str):
    path = get_uploaded_file_path(file_id)
    if not os.path.exists(path):
        flash("Fichier DICOM introuvable ou expiré.")
        return redirect(url_for("index"))

    ds = pydicom.dcmread(path)
    wc_default, ww_default = get_windowing(ds)
    if wc_default is None or ww_default is None:
        wc_default = float(np.mean(ds.pixel_array))
        ww_default = float(np.max(ds.pixel_array) - np.min(ds.pixel_array))

    wc = request.args.get("wc", str(wc_default))
    ww = request.args.get("ww", str(ww_default))

    try:
        window_center = float(wc)
    except ValueError:
        window_center = wc_default
    try:
        window_width = float(ww)
    except ValueError:
        window_width = ww_default

    image_data = dicom_to_base64(ds, window_center, window_width)

    # Extract metadata
    patient_name = ds.get("PatientName", "N/A")
    patient_id = ds.get("PatientID", "N/A")
    patient_birth_date = ds.get("PatientBirthDate", "N/A")
    study_description = ds.get("StudyDescription", "N/A")
    acquisition_date_time = ds.get("AcquisitionDateTime", ds.get("StudyDate", "N/A"))
    institution_name = ds.get("InstitutionName", "N/A")
    slice_count = 1  # For single DICOM file
    zoom = 100  # Default zoom

    return render_template(
        "image_view.html",
        file_id=file_id,
        patient_name=patient_name,
        patient_id=patient_id,
        patient_birth_date=patient_birth_date,
        study_description=study_description,
        acquisition_date_time=acquisition_date_time,
        institution_name=institution_name,
        window_center=window_center,
        window_width=window_width,
        image_data=image_data,
        slice_count=slice_count,
        zoom=zoom,
    )

@app.route("/recent", methods=["GET"])
def recent():
    studies = []
    total_size = 0
    upload_folder = app.config["UPLOAD_FOLDER"]
    for filename in os.listdir(upload_folder):
        if filename.endswith(".dcm"):
            file_id = filename[:-4]  # remove .dcm
            path = os.path.join(upload_folder, filename)
            try:
                ds = pydicom.dcmread(path, stop_before_pixels=True)  # Read metadata only for speed
                patient_name = str(ds.get("PatientName", "Unknown"))
                modality = ds.get("Modality", "UNK")
                study_date = ds.get("StudyDate", "N/A")
                if study_date != "N/A":
                    study_date = datetime.strptime(study_date, "%Y%m%d").strftime("%b %d, %Y")
                else:
                    study_date = "N/A"
                file_size = os.path.getsize(path)
                total_size += file_size
                file_size_mb = round(file_size / (1024 * 1024), 1)
                upload_date = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%b %d, %Y")
                # For thumbnail, need to read pixels
                ds_full = pydicom.dcmread(path)
                thumbnail = dicom_to_thumbnail(ds_full)
                studies.append({
                    "file_id": file_id,
                    "patient_name": patient_name,
                    "modality": modality,
                    "study_date": study_date,
                    "upload_date": upload_date,
                    "file_size_mb": file_size_mb,
                    "thumbnail": thumbnail,
                })
            except Exception as e:
                print(f"Error reading {filename}: {e}")
                continue
    studies.sort(key=lambda x: x["upload_date"], reverse=True)  # Sort by upload date descending
    total_studies = len(studies)
    total_size_gb = round(total_size / (1024**3), 1)
    return render_template("recent.html", studies=studies, total_studies=total_studies, total_size_gb=total_size_gb)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
