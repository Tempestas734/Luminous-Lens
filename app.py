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
MAX_RENDER_DIMENSION = 1600
MAX_THUMBNAIL_DIMENSION = 256
MAX_TAG_VALUE_LENGTH = 240

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


def retirer_televersements_session(file_ids: list[str]) -> None:
    if not file_ids:
        return
    file_ids_set = set(file_ids)
    uploads = obtenir_televersements_session()
    session[SESSION_UPLOADS_KEY] = [
        item for item in uploads if item.get("file_id") not in file_ids_set
    ]


def normaliser_requete_tag(query: str) -> str:
    return query.strip().lower()


def extraire_nombre_depuis_valeur(value, frame_index: int = 0) -> Optional[float]:
    if isinstance(value, pydicom.multival.MultiValue):
        if not value:
            return None
        if len(value) > frame_index:
            value = value[frame_index]
        else:
            value = value[0]
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def obtenir_fenetrage_sequence(item) -> Tuple[Optional[float], Optional[float]]:
    if item is None:
        return None, None

    frame_voi_lut = item.get("FrameVOILUTSequence")
    if frame_voi_lut:
        voi_item = frame_voi_lut[0]
        wc = extraire_nombre_depuis_valeur(voi_item.get("WindowCenter"))
        ww = extraire_nombre_depuis_valeur(voi_item.get("WindowWidth"))
        if wc is not None and ww is not None:
            return wc, ww

    wc = extraire_nombre_depuis_valeur(item.get("WindowCenter"))
    ww = extraire_nombre_depuis_valeur(item.get("WindowWidth"))
    return wc, ww


def obtenir_fenetrage(ds: pydicom.dataset.Dataset, frame_index: int = 0) -> Tuple[Optional[float], Optional[float]]:
    per_frame_groups = ds.get("PerFrameFunctionalGroupsSequence")
    if per_frame_groups and len(per_frame_groups) > frame_index:
        wc, ww = obtenir_fenetrage_sequence(per_frame_groups[frame_index])
        if wc is not None and ww is not None:
            return wc, ww

    shared_groups = ds.get("SharedFunctionalGroupsSequence")
    if shared_groups:
        wc, ww = obtenir_fenetrage_sequence(shared_groups[0])
        if wc is not None and ww is not None:
            return wc, ww

    wc = extraire_nombre_depuis_valeur(ds.get("WindowCenter", None), frame_index)
    ww = extraire_nombre_depuis_valeur(ds.get("WindowWidth", None), frame_index)
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


def reduire_taille_image(image: Image.Image, max_dimension: int) -> Image.Image:
    if max(image.size) <= max_dimension:
        return image
    reduced = image.copy()
    reduced.thumbnail((max_dimension, max_dimension), Image.LANCZOS)
    return reduced


def obtenir_nombre_coupes(ds: pydicom.dataset.Dataset) -> int:
    number_of_frames = ds.get("NumberOfFrames")
    try:
        return max(1, int(number_of_frames))
    except (TypeError, ValueError):
        return 1


def normaliser_index_coupe(frame_index: Optional[int], slice_count: int) -> int:
    if frame_index is None:
        return 0
    return max(0, min(frame_index, max(slice_count - 1, 0)))


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
        return arr

    return preparer_tableau_pour_image(arr.reshape(arr.shape[-2], arr.shape[-1]))


def extraire_coupe_pour_affichage(arr: np.ndarray, frame_index: int) -> np.ndarray:
    arr = np.asarray(arr)

    while arr.ndim > 4 and 1 in arr.shape:
        arr = np.squeeze(arr, axis=tuple(index for index, size in enumerate(arr.shape) if size == 1))

    if arr.ndim <= 2:
        return preparer_tableau_pour_image(arr)

    if arr.ndim == 3:
        if arr.shape[-1] in (3, 4):
            return preparer_tableau_pour_image(arr)
        index = normaliser_index_coupe(frame_index, arr.shape[0])
        return preparer_tableau_pour_image(arr[index])

    if arr.ndim == 4:
        if arr.shape[-1] in (3, 4):
            index = normaliser_index_coupe(frame_index, arr.shape[0])
            return preparer_tableau_pour_image(arr[index])
        index = normaliser_index_coupe(frame_index, arr.shape[0])
        return extraire_coupe_pour_affichage(arr[index], 0)

    return preparer_tableau_pour_image(arr)


def charger_dicom(file_id: str, *, stop_before_pixels: bool = False) -> Optional[pydicom.dataset.Dataset]:
    path = obtenir_chemin_fichier_televerse(file_id)
    if not os.path.exists(path):
        return None
    return pydicom.dcmread(path, stop_before_pixels=stop_before_pixels)


def obtenir_fenetrage_par_defaut(ds: pydicom.dataset.Dataset, frame_index: int = 0) -> Tuple[float, float]:
    wc_default, ww_default = obtenir_fenetrage(ds, frame_index)
    if wc_default is not None and ww_default is not None:
        return wc_default, ww_default

    pixel_array = reechantillonner_tableau_pixels(ds, ds.pixel_array.astype(np.float32))
    pixel_array = extraire_coupe_pour_affichage(pixel_array, frame_index)
    wc_default = float(np.mean(pixel_array))
    ww_default = float(np.max(pixel_array) - np.min(pixel_array))
    if ww_default <= 0:
        ww_default = 1.0
    return wc_default, ww_default


def calculer_bornes_fenetrage(window_center: float, window_width: float) -> Dict[str, float]:
    safe_width = max(float(window_width), 1.0)
    center_span = max(150.0, safe_width, abs(float(window_center)) * 0.5)
    width_max = max(1024.0, safe_width * 2.0, abs(float(window_center)) * 2.0)
    return {
        "wc_min": float(window_center) - center_span,
        "wc_max": float(window_center) + center_span,
        "ww_min": 1.0,
        "ww_max": width_max,
    }


def formater_date_dicom(study_date: str) -> str:
    if not study_date or study_date == "N/A":
        return "N/A"
    try:
        return datetime.strptime(study_date, "%Y%m%d").strftime("%b %d, %Y")
    except ValueError:
        return study_date


def dicom_vers_base64(
    ds: pydicom.dataset.Dataset, center: float, width: float, frame_index: int = 0
) -> str:
    pixel_array = ds.pixel_array.astype(np.float32)
    pixel_array = reechantillonner_tableau_pixels(ds, pixel_array)
    pixel_array = extraire_coupe_pour_affichage(pixel_array, frame_index)
    pixel_array = appliquer_fenetre(pixel_array, center, width)
    if getattr(ds, "PhotometricInterpretation", "MONOCHROME2") == "MONOCHROME1":
        pixel_array = 1.0 - pixel_array
    image = Image.fromarray((pixel_array * 255).astype(np.uint8))
    image = reduire_taille_image(image, MAX_RENDER_DIMENSION)
    buffered = BytesIO()
    image.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("ascii")


def dicom_vers_vignette(ds: pydicom.dataset.Dataset) -> str:
    pixel_array = ds.pixel_array.astype(np.float32)
    pixel_array = reechantillonner_tableau_pixels(ds, pixel_array)
    pixel_array = extraire_coupe_pour_affichage(pixel_array, 0)
    # Use default windowing for thumbnail
    wc, ww = obtenir_fenetrage(ds, 0)
    if wc is None or ww is None:
        wc = float(np.mean(pixel_array))
        ww = float(np.max(pixel_array) - np.min(pixel_array))
    pixel_array = appliquer_fenetre(pixel_array, wc, ww)
    if getattr(ds, "PhotometricInterpretation", "MONOCHROME2") == "MONOCHROME1":
        pixel_array = 1.0 - pixel_array
    image = Image.fromarray((pixel_array * 255).astype(np.uint8))
    image = reduire_taille_image(image, MAX_THUMBNAIL_DIMENSION)
    buffered = BytesIO()
    image.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("ascii")


def formater_valeur_dicom(value) -> str:
    if isinstance(value, (bytes, bytearray)):
        return f"<binary data: {len(value)} bytes>"

    if isinstance(value, (list, tuple, pydicom.multival.MultiValue)):
        rendered = ", ".join(str(v) for v in value) if value else ""
    else:
        rendered = str(value)

    if len(rendered) > MAX_TAG_VALUE_LENGTH:
        return f"{rendered[:MAX_TAG_VALUE_LENGTH]}..."
    return rendered


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
            file_size = request.content_length or 0
            if obtenir_total_octets_session() + file_size > MAX_SESSION_BYTES:
                flash("Limite de session atteinte : supprimez des fichiers ou rafraichissez la page.")
                return redirect(url_for("accueil"))

            file_id = str(uuid.uuid4())
            path = obtenir_chemin_fichier_televerse(file_id)
            try:
                file.save(path)
                file_size = os.path.getsize(path)
                if obtenir_total_octets_session() + file_size > MAX_SESSION_BYTES:
                    os.remove(path)
                    flash("Limite de session atteinte : supprimez des fichiers ou rafraichissez la page.")
                    return redirect(url_for("accueil"))
                pydicom.dcmread(path, stop_before_pixels=True)
            except Exception:
                if os.path.exists(path):
                    os.remove(path)
                flash("Le fichier selectionne n'est pas un DICOM valide.")
                return redirect(url_for("accueil"))
            ajouter_televersement_session(file_id, file.filename, file_size)
            return redirect(url_for("vue_image", file_id=file_id))
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

    slice_count = obtenir_nombre_coupes(ds)

    try:
        current_frame = normaliser_index_coupe(request.args.get("frame", default=0, type=int), slice_count)
        wc_default, ww_default = obtenir_fenetrage_par_defaut(ds, current_frame)
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
        image_data = dicom_vers_base64(ds, window_center, window_width, current_frame)
    except Exception:
        flash("Le rendu de l'image DICOM a échoué.")
        return redirect(url_for("accueil"))
    window_bounds = calculer_bornes_fenetrage(window_center, window_width)
    tag_value = trouver_valeur_tag(ds, tag_query) if tag_query.strip() else None
    if tag_query and tag_value is None:
        flash(f"Tag non trouvé pour '{tag_query}'.")

    tags = construire_table_tags(ds)
    # Extract summary metadata
    modality = ds.get("Modality", "N/A")
    patient_id = ds.get("PatientID", "N/A")
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
        window_bounds=window_bounds,
        default_window_center=wc_default,
        default_window_width=ww_default,
        tag_query=tag_query,
        tag_value=tag_value,
        tags=tags,
        current_frame=current_frame,
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

    slice_count = obtenir_nombre_coupes(ds)
    frame_index = normaliser_index_coupe(request.args.get("frame", default=0, type=int), slice_count)
    wc_default, ww_default = obtenir_fenetrage_par_defaut(ds, frame_index)
    use_frame_defaults = request.args.get("use_frame_defaults", "").lower() in {"1", "true", "yes"}

    wc = request.args.get("wc", str(wc_default))
    ww = request.args.get("ww", str(ww_default))

    try:
        window_center = wc_default if use_frame_defaults else float(wc)
    except ValueError:
        window_center = wc_default
    try:
        window_width = ww_default if use_frame_defaults else float(ww)
    except ValueError:
        window_width = ww_default

    try:
        image_data = dicom_vers_base64(ds, window_center, window_width, frame_index)
    except Exception:
        return {"error": "Unable to render image"}, 400
    return {
        "image_data": image_data,
        "frame_index": frame_index,
        "slice_count": slice_count,
        "window_center": window_center,
        "window_width": window_width,
        "window_bounds": calculer_bornes_fenetrage(window_center, window_width),
        "default_window_center": wc_default,
        "default_window_width": ww_default,
    }

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

    slice_count = obtenir_nombre_coupes(ds)
    current_frame = normaliser_index_coupe(request.args.get("frame", default=0, type=int), slice_count)
    wc_default, ww_default = obtenir_fenetrage_par_defaut(ds, current_frame)

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
        image_data = dicom_vers_base64(ds, window_center, window_width, current_frame)
    except Exception:
        flash("Le rendu de l'image DICOM a échoué.")
        return redirect(url_for("accueil"))

    window_bounds = calculer_bornes_fenetrage(window_center, window_width)

    # Extract metadata
    patient_name = ds.get("PatientName", "N/A")
    patient_id = ds.get("PatientID", "N/A")
    patient_birth_date = ds.get("PatientBirthDate", "N/A")
    study_description = ds.get("StudyDescription", "N/A")
    acquisition_date_time = ds.get("AcquisitionDateTime", ds.get("StudyDate", "N/A"))
    institution_name = ds.get("InstitutionName", "N/A")
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
        window_bounds=window_bounds,
        image_data=image_data,
        slice_count=slice_count,
        current_frame=current_frame,
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


@app.route("/recent/delete", methods=["POST"])
def supprimer_archive():
    action = request.form.get("action", "selected")
    upload_folder = app.config["UPLOAD_FOLDER"]

    if action == "all":
        file_ids = [
            filename[:-4]
            for filename in os.listdir(upload_folder)
            if filename.endswith(".dcm")
        ]
    else:
        file_ids = [file_id for file_id in request.form.getlist("file_ids") if file_id]

    if not file_ids:
        flash("Aucune image selectionnee a supprimer.")
        return redirect(url_for("recents"))

    deleted_file_ids = []
    for file_id in file_ids:
        path = obtenir_chemin_fichier_televerse(file_id)
        if os.path.exists(path):
            os.remove(path)
            deleted_file_ids.append(file_id)

    retirer_televersements_session(deleted_file_ids)

    if action == "all":
        flash("Toute l'archive a ete supprimee.")
    else:
        flash(f"{len(deleted_file_ids)} image(s) supprimee(s) de l'archive.")
    return redirect(url_for("recents"))

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes"},
    )
