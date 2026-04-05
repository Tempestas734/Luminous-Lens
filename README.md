# Luminous Lens

A modern web-based DICOM medical image viewer built with Flask. Upload, view, and analyze DICOM files with adjustable windowing and comprehensive metadata display.

## Features

- **DICOM Upload**: Secure file upload with support for .dcm and .dicom formats (max 50MB)
- **Image Visualization**:
  - Automatic conversion to PNG for web display
  - Adjustable windowing (center/width) for optimal contrast
  - Support for MONOCHROME1 and MONOCHROME2 photometric interpretations
  - Thumbnail generation for quick browsing
- **Metadata Display**:
  - Complete DICOM tag table with hex codes, names, VR, and values
  - Interactive tag search by name or hex code
  - Patient information (name, ID, birth date)
  - Study details (description, date, UID)
  - Institution information
- **Recent Studies**: Browse uploaded files with thumbnails, sorted by upload date
- **Responsive Design**: Modern UI built with Tailwind CSS

## Installation

### Prerequisites
- Python 3.8 or higher
- pip package manager

### Setup
1. Clone the repository:
   ```bash
   git clone https://github.com/Tempestas734/Luminous-Lens.git
   cd Luminous-Lens
   ```

2. Create a virtual environment:
   ```bash
   python -m venv .venv
   # On Windows:
   .venv\Scripts\activate
   # On macOS/Linux:
   source .venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Start the application:
   ```bash
   python app.py
   ```

2. Open your browser and navigate to `http://localhost:5000`

3. Upload a DICOM file using the upload form

4. View the image with adjustable windowing controls

5. Explore metadata in the tags table

6. Search for specific DICOM tags

7. Browse recent uploads in the "Recent" section

## Technologies

- **Backend**: Flask (Python web framework)
- **DICOM Processing**: pydicom library
- **Image Processing**: Pillow (PIL) and NumPy
- **Frontend**: HTML5, Tailwind CSS, JavaScript
- **Icons**: Material Symbols Outlined

## Project Structure

```
Luminous-Lens/
├── app.py                 # Main Flask application
├── dicom_1.py            # DICOM utility script
├── requirements.txt       # Python dependencies
├── .gitignore            # Git ignore rules
├── static/
│   ├── style.css         # Custom CSS styles
│   ├── upload.js         # Upload functionality
│   └── viewer.js         # Image viewer controls
├── templates/
│   ├── index.html        # Upload page
│   ├── view.html         # Main viewer page
│   ├── image_view.html   # Image-only view
│   └── recent.html       # Recent uploads page
└── uploads/              # Uploaded DICOM files (gitignored)
```

## API Endpoints

- `GET /` - Upload page
- `POST /` - Handle file upload
- `GET /view/<file_id>` - View DICOM with metadata
- `GET /image/<file_id>` - Image-only view
- `GET /image_data/<file_id>` - JSON image data endpoint
- `GET /recent` - Recent uploads page

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This software is for educational and research purposes. It is not intended for clinical use without proper validation and regulatory approval.