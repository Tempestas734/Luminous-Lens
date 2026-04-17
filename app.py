import base64
import os
import re
import uuid
from datetime import datetime
from io import BytesIO
from typing import Dict, Optional, Tuple

import numpy as np
import pydicom
from flask import Flask, flash, redirect, render_template, request, session, url_for
from PIL import Image
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"dcm", "dicom"}
MAX_CONTENT_LENGTH = 50 * 1024 * 1024
MAX_SESSION_BYTES = 2 * 1024 * 1024 * 1024
SESSION_UPLOADS_KEY = "session_uploads"

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-me")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def fichier_autorise(filename: str) -> bool:
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return extension in ALLOWED_EXTENSIONS


def obtenir_televersements_session() -> list:
    uploads = session.get(SESSION_UPLOADS_KEY, [])
    uploads_valides = [
        item for item in uploads
        if os.path.exists(obtenir_chemin_fichier_televerse(item.get("file_id", "")))
    ]
    if len(uploads_valides) != len(uploads):
        session[SESSION_UPLOADS_KEY] = uploads_valides
    return uploads_valides


def obtenir_total_octets_session() -> int:
    return sum(item.get("size", 0) for item in obtenir_televersements_session())


def ajouter_televersement_session(file_id: str, filename: str, size: int) -> None:
    uploads = obtenir_televersements_session()
    uploads.append(
        {
            "file_id": file_id,
            "filename": filename,
            "size": size,
            "uploaded_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    session[SESSION_UPLOADS_KEY] = uploads


def normaliser_requete_tag(query: str) -> str:
    return query.strip().lower()


def obtenir_fenetrage(ds: pydicom.dataset.Dataset) -> Tuple[Optional[float], Optional[float]]:
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


def reechantillonner_tableau_pixels(ds: pydicom.dataset.Dataset, arr: np.ndarray) -> np.ndarray:
    slope = float(ds.get("RescaleSlope", 1.0))
    intercept = float(ds.get("RescaleIntercept", 0.0))
    if slope != 1.0 or intercept != 0.0:
        arr = arr.astype(np.float32) * slope + intercept
    return arr


def appliquer_fenetre(arr: np.ndarray, center: float, width: float) -> np.ndarray:
    if width <= 0:
        width = 1.0
    low = center - width / 2.0
    high = center + width / 2.0
    arr = np.clip(arr, low, high)
    arr = (arr - low) / max(high - low, 1.0)
    return arr


def preparer_tableau_pour_image(arr: np.ndarray) -> np.ndarray:
    arr = np.asarray(arr)

    # Drop useless singleton dimensions while preserving image semantics.
    while arr.ndim > 3 and 1 in arr.shape:
        arr = np.squeeze(arr, axis=tuple(index for index, size in enumerate(arr.shape) if size == 1))

    if arr.ndim == 0:
        raise ValueError("Le tableau DICOM ne contient pas de donnees image exploitables.")

    if arr.ndim == 1:
        return arr[np.newaxis, :]

    if arr.ndim == 2:
        return arr

    if arr.ndim == 3:
        if arr.shape[-1] in (3, 4):
            return arr
        if arr.shape[0] == 1:
            return preparer_tableau_pour_image(arr[0])
        if arr.shape[-1] == 1:
            return preparer_tableau_pour_image(arr[..., 0])
        return preparer_tableau_pour_image(arr[0])

    return preparer_tableau_pour_image(arr.reshape(arr.shape[-2], arr.shape[-1]))


def charger_dicom(file_id: str, *, stop_before_pixels: bool = False) -> Optional[pydicom.dataset.Dataset]:
    path = obtenir_chemin_fichier_televerse(file_id)
    if not os.path.exists(path):
        return None
    return pydicom.dcmread(path, stop_before_pixels=stop_before_pixels)


def obtenir_fenetrage_par_defaut(ds: pydicom.dataset.Dataset) -> Tuple[float, float]:
    wc_default, ww_default = obtenir_fenetrage(ds)
    if wc_default is not None and ww_default is not None:
        return wc_default, ww_default

    pixel_array = reechantillonner_tableau_pixels(ds, ds.pixel_array.astype(np.float32))
    pixel_array = preparer_tableau_pour_image(pixel_array)
    wc_default = float(np.mean(pixel_array))
    ww_default = float(np.max(pixel_array) - np.min(pixel_array))
    if ww_default <= 0:
        ww_default = 1.0
    return wc_default, ww_default


def formater_date_dicom(study_date: str) -> str:
    if not study_date or study_date == "N/A":
        return "N/A"
    try:
        return datetime.strptime(study_date, "%Y%m%d").strftime("%b %d, %Y")
    except ValueError:
        return study_date


def dicom_vers_base64(ds: pydicom.dataset.Dataset, center: float, width: float) -> str:
    pixel_array = ds.pixel_array.astype(np.float32)
    pixel_array = reechantillonner_tableau_pixels(ds, pixel_array)
    pixel_array = appliquer_fenetre(pixel_array, center, width)
    pixel_array = preparer_tableau_pour_image(pixel_array)
    if getattr(ds, "PhotometricInterpretation", "MONOCHROME2") == "MONOCHROME1":
        pixel_array = 1.0 - pixel_array
    image = Image.fromarray((pixel_array * 255).astype(np.uint8))
    buffered = BytesIO()
    image.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("ascii")


def dicom_vers_vignette(ds: pydicom.dataset.Dataset) -> str:
    pixel_array = ds.pixel_array.astype(np.float32)
    pixel_array = reechantillonner_tableau_pixels(ds, pixel_array)
    # Use default windowing for thumbnail
    wc, ww = obtenir_fenetrage(ds)
    if wc is None or ww is None:
        wc = float(np.mean(pixel_array))
        ww = float(np.max(pixel_array) - np.min(pixel_array))
    pixel_array = appliquer_fenetre(pixel_array, wc, ww)
    pixel_array = preparer_tableau_pour_image(pixel_array)
    if getattr(ds, "PhotometricInterpretation", "MONOCHROME2") == "MONOCHROME1":
        pixel_array = 1.0 - pixel_array
    image = Image.fromarray((pixel_array * 255).astype(np.uint8))
    # Resize to thumbnail
    image = image.resize((256, 256), Image.LANCZOS)
    buffered = BytesIO()
    image.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("ascii")


def formater_valeur_dicom(value) -> str:
    if isinstance(value, (list, tuple, pydicom.multival.MultiValue)):
        return ", ".join(str(v) for v in value) if value else ""
    return str(value)


def construire_table_tags(ds: pydicom.dataset.Dataset) -> list[Dict[str, str]]:
    rows = []
    for elem in ds.iterall():
        rows.append(
            {
                "tag": f"({elem.tag.group:04X},{elem.tag.element:04X})",
                "name": elem.keyword or elem.name,
                "vr": elem.VR,
                "value": formater_valeur_dicom(elem.value),
            }
        )
    return rows


def trouver_valeur_tag(ds: pydicom.dataset.Dataset, query: str) -> Optional[str]:
    normalized = normaliser_requete_tag(query)
    if not normalized:
        return None

    tag_pattern = re.compile(r"^\(?([0-9a-fA-F]{4})\s*,\s*([0-9a-fA-F]{4})\)?$")
    match = tag_pattern.match(query.strip())
    if match:
        group = int(match.group(1), 16)
        element = int(match.group(2), 16)
        tag = pydicom.tag.Tag(group, element)
        if tag in ds:
            return formater_valeur_dicom(ds[tag].value)
        return None

    query_lower = normalized
    for elem in ds.iterall():
        name = (elem.keyword or elem.name or "").lower()
        if query_lower == name or query_lower in name:
            return formater_valeur_dicom(elem.value)
    return None


def obtenir_chemin_fichier_televerse(file_id: str) -> str:
    return os.path.join(app.config["UPLOAD_FOLDER"], f"{secure_filename(file_id)}.dcm")

@app.route("/", methods=["GET", "POST"])
def accueil():
    if request.method == "POST":
        if "dicom_file" not in request.files:
            flash("Aucun fichier sélectionné.")
            return redirect(url_for("accueil"))
        file = request.files["dicom_file"]
        if file.filename == "":
            flash("Aucun fichier sélectionné.")
            return redirect(url_for("accueil"))
        if file and fichier_autorise(file.filename):
            file_size = len(file.read())
            file.seek(0)
            if obtenir_total_octets_session() + file_size > MAX_SESSION_BYTES:
                flash("Limite de session atteinte : supprimez des fichiers ou rafraichissez la page.")
                return redirect(url_for("accueil"))

            file_id = str(uuid.uuid4())
            path = obtenir_chemin_fichier_televerse(file_id)
            try:
                file.save(path)
                pydicom.dcmread(path, stop_before_pixels=True)
            except Exception:
                if os.path.exists(path):
                    os.remove(path)
                flash("Le fichier selectionne n'est pas un DICOM valide.")
                return redirect(url_for("accueil"))
            ajouter_televersement_session(file_id, file.filename, file_size)
            return redirect(url_for("voir_dicom", file_id=file_id))
        flash("Format non autorisé. Utilisez un fichier DICOM (.dcm ou .dicom).")
        return redirect(url_for("accueil"))

    session_uploads = obtenir_televersements_session()
    session_total_mb = round(obtenir_total_octets_session() / (1024 * 1024), 1)
    session_limit_gb = round(MAX_SESSION_BYTES / (1024 * 1024 * 1024), 1)
    return render_template(
        "index.html",
        session_uploads=session_uploads,
        session_total_mb=session_total_mb,
        session_limit_gb=session_limit_gb,
        session_upload_count=len(session_uploads),
    )

@app.route("/clear_session", methods=["POST"])
def vider_session():
    for item in obtenir_televersements_session():
        path = obtenir_chemin_fichier_televerse(item.get("file_id", ""))
        if os.path.exists(path):
            os.remove(path)
    session.pop(SESSION_UPLOADS_KEY, None)
    flash("Session réinitialisée avec succès.")
    return redirect(url_for("accueil"))

@app.route("/view/<file_id>", methods=["GET"])
def voir_dicom(file_id: str):
    try:
        ds = charger_dicom(file_id)
    except Exception:
        flash("Impossible de lire ce fichier DICOM.")
        return redirect(url_for("accueil"))
    if ds is None:
        flash("Fichier DICOM introuvable ou expiré.")
        return redirect(url_for("accueil"))

    try:
        wc_default, ww_default = obtenir_fenetrage_par_defaut(ds)
    except Exception:
        flash("Le rendu de l'image DICOM a échoué.")
        return redirect(url_for("accueil"))

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

    try:
        image_data = dicom_vers_base64(ds, window_center, window_width)
    except Exception:
        flash("Le rendu de l'image DICOM a échoué.")
        return redirect(url_for("accueil"))
    tag_value = trouver_valeur_tag(ds, tag_query) if tag_query.strip() else None
    if tag_query and tag_value is None:
        flash(f"Tag non trouvé pour '{tag_query}'.")

    tags = construire_table_tags(ds)
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
def donnees_image(file_id: str):
    try:
        ds = charger_dicom(file_id)
    except Exception:
        return {"error": "Invalid DICOM file"}, 400
    if ds is None:
        return {"error": "File not found"}, 404

    wc_default, ww_default = obtenir_fenetrage_par_defaut(ds)

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

    try:
        image_data = dicom_vers_base64(ds, window_center, window_width)
    except Exception:
        return {"error": "Unable to render image"}, 400
    return {"image_data": image_data}

@app.route("/image/<file_id>", methods=["GET"])
def vue_image(file_id: str):
    try:
        ds = charger_dicom(file_id)
    except Exception:
        flash("Impossible de lire ce fichier DICOM.")
        return redirect(url_for("accueil"))
    if ds is None:
        flash("Fichier DICOM introuvable ou expiré.")
        return redirect(url_for("accueil"))

    wc_default, ww_default = obtenir_fenetrage_par_defaut(ds)

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

    try:
        image_data = dicom_vers_base64(ds, window_center, window_width)
    except Exception:
        flash("Le rendu de l'image DICOM a échoué.")
        return redirect(url_for("accueil"))

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
def recents():
    studies = []
    total_size = 0
    upload_folder = app.config["UPLOAD_FOLDER"]
    for filename in os.listdir(upload_folder):
        if filename.endswith(".dcm"):
            file_id = filename[:-4]  # remove .dcm
            path = os.path.join(upload_folder, filename)
            try:
                ds = pydicom.dcmread(path, stop_before_pixels=True)
                patient_name = str(ds.get("PatientName", "Unknown"))
                modality = ds.get("Modality", "UNK")
                study_date = formater_date_dicom(ds.get("StudyDate", "N/A"))
                file_size = os.path.getsize(path)
                total_size += file_size
                file_size_mb = round(file_size / (1024 * 1024), 1)
                upload_timestamp = os.path.getmtime(path)
                upload_date = datetime.fromtimestamp(upload_timestamp).strftime("%b %d, %Y")
                ds_full = pydicom.dcmread(path)
                thumbnail = dicom_vers_vignette(ds_full)
                studies.append({
                    "file_id": file_id,
                    "patient_name": patient_name,
                    "modality": modality,
                    "study_date": study_date,
                    "upload_date": upload_date,
                    "upload_timestamp": upload_timestamp,
                    "file_size_mb": file_size_mb,
                    "thumbnail": thumbnail,
                })
            except Exception:
                continue
    studies.sort(key=lambda x: x["upload_timestamp"], reverse=True)
    total_studies = len(studies)
    total_size_gb = round(total_size / (1024**3), 1)
    return render_template("recent.html", studies=studies, total_studies=total_studies, total_size_gb=total_size_gb)

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes"},
    )
