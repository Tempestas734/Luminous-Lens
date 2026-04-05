# Luminous Lens

A sophisticated web-based DICOM image viewer built with Flask, designed for medical professionals to visualize and analyze DICOM images directly in the browser without specialized software.

## Features

- **DICOM Upload & Processing**: Support for .dcm, .dicom files and compressed .zip series
- **Metadata Extraction**: Automatic extraction and display of DICOM tags with search functionality
- **Image Visualization**: Interactive DICOM image viewer with windowing controls (brightness/contrast)
- **Session Management**: Upload tracking with storage limits (2GB per session) and session clearing
- **Responsive Design**: Modern Material Design-inspired UI with Tailwind CSS
- **Archive View**: Gallery view of uploaded studies with thumbnails

## Technologies

- **Backend**: Python Flask
- **Frontend**: HTML5, Tailwind CSS, JavaScript
- **DICOM Processing**: pydicom, PIL (Pillow)
- **Styling**: Material Symbols, Custom color palette
- **Deployment**: Ready for web server deployment

## Installation

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

3. Upload DICOM files using drag & drop or the browse button

4. View metadata, visualize images, and manage your session

## Project Structure

```
Luminous-Lens/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── static/
│   ├── style.css         # Shared CSS styles
│   ├── app.js            # Consolidated JavaScript
│   └── tailwind-config.js # Tailwind configuration
├── templates/
│   ├── base.html         # Base template with navbar/footer
│   ├── index.html        # Upload page
│   ├── view.html         # Metadata viewer
│   ├── image_view.html   # DICOM image viewer
│   ├── recent.html       # Archive/gallery view
│   ├── _navbar.html      # Navigation component
│   └── _footer.html      # Footer component
└── uploads/              # Uploaded files directory
```

## Features in Detail

### Session Management
- Tracks uploaded files with timestamps and sizes
- Enforces 2GB storage limit per session
- Provides clear session functionality
- Displays real-time storage usage

### DICOM Processing
- Validates DICOM files and extracts metadata
- Handles compressed series (.zip files)
- Converts images for web display
- Maintains patient data privacy

### User Interface
- Clean, professional design suitable for medical use
- Responsive layout for desktop and mobile
- Intuitive drag-and-drop upload
- Interactive image controls

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This software is for educational and research purposes. It is not intended for clinical use without proper validation and regulatory approval. Always consult with qualified medical professionals for diagnostic decisions.
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