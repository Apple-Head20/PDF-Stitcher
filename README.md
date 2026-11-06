# PDF Stitcher

**A lightweight Python desktop application for merging PDF documents while preserving their original page content and visual quality.**

PDF Stitcher is a GUI-based PDF merging utility built with **Python, Tkinter, and PyMuPDF**. It allows users to combine multiple PDF documents into a single file while maintaining their original page order, dimensions, text, vector graphics, and images.

Unlike image-based PDF merging methods, PDF Stitcher copies native PDF pages directly without converting them into raster images.

The application also includes optional page-by-page verification to ensure that the merged output matches its source documents before the final file is saved.

## Features

- **Native PDF Merging** — Combines PDF pages without rasterizing or resizing them.
- **Multiple PDF Support** — Merge 20 or more PDF documents in a single operation, subject to available system resources.
- **Custom File Ordering** — Rearrange input PDFs using drag-to-reorder or Move Up/Down controls.
- **Visual Verification** — Optionally compares the rendered appearance of every source page against its corresponding merged page.
- **Text Verification** — Compares extractable text from source and merged pages when verification is enabled.
- **Page Count Validation** — Checks that the merged document contains the expected number of pages.
- **Source File Integrity Checks** — Detects changes to source files between selection and merging.
- **Safe Output Handling** — Writes to a temporary file and publishes the result only after validation succeeds.
- **Background Processing** — Performs merging in a worker thread to keep the GUI responsive.
- **Progress Tracking** — Displays merging and verification progress.
- **Error Handling** — Rejects password-protected, empty, or damaged PDFs during initial inspection.
- **Lightweight Interface** — Uses Tkinter and ttk without requiring a browser or web server.

## Technology Stack

| Technology | Purpose |
|---|---|
| Python | Core application logic |
| Tkinter | Desktop graphical interface |
| ttk | Native-style widgets and progress indicators |
| PyMuPDF (`fitz`) | PDF reading, merging, rendering, and verification |
| threading | Background merge execution |
| queue | Communication between worker and GUI |
| pathlib | File path management |
| tempfile | Temporary output creation |

Only **PyMuPDF** requires installation through pip. The remaining modules are included in Python's standard library.

## How It Works

```text
           Select PDF Documents
                    |
                    v
           Inspect Source PDFs
                    |
                    v
           Arrange File Order
                    |
                    v
              Start Merge
                    |
                    v
          Create Temporary PDF
                    |
                    v
          Copy Native PDF Pages
                    |
                    v
           Validate Page Count
                    |
                    v
         Optional Full Verification
          /                    \
     Text Check           Visual Check
          \                    /
                    |
                    v
          Publish Verified PDF
                    |
                    v
              Merge Complete
```

### Native-Page Merging

PDF Stitcher uses PyMuPDF's `insert_pdf()` functionality to copy pages directly from source documents into the merged document.

This approach preserves native PDF content rather than converting pages into screenshots or newly generated images.

The implementation also requests copying of links, annotations, and form widgets.

### Page-by-Page Verification

When verification is enabled, the application performs additional checks after merging.

**1. Page count validation**

The output must contain the same total number of pages as the combined source documents.

**2. Text verification**

The application compares extractable text from each source page with the corresponding merged page.

**3. Visual verification**

Every source page and its merged counterpart are rendered at 72 DPI using PyMuPDF.

Their dimensions and rendered image digests are compared to detect visual differences.

If verification fails, the application reports an error and does not publish the temporary output as the final file.

**Note:** This verifies rendered appearance and extractable text at the implemented settings. It is not a byte-for-byte comparison of all internal PDF objects, metadata, or document-level features.

## Installation

### Prerequisites

- Python 3.10 or later with a compatible PyMuPDF version
- Tkinter support
- Windows, Linux, or macOS with a graphical desktop environment

The interface is primarily styled for Windows, although it uses cross-platform Python GUI libraries.

### 1. Clone the Repository

```bash
git clone https://github.com/Apple-Head20/PDF-Stitcher.git
cd PDF-Stitcher
```

### 2. Create a Virtual Environment

On Windows:

```powershell
python -m venv venv
```

Activate the environment:

```powershell
.\venv\Scripts\Activate.ps1
```

On Linux or macOS:

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
python -m pip install -r requirements.txt
```

Alternatively:

```bash
python -m pip install pymupdf
```

### 4. Run the Application

```bash
python pdf_stitcher.py
```

The PDF Stitcher graphical interface will open.

## Usage

### Step 1 — Add PDFs

Click **+ Add PDFs** and select one or more PDF documents.

The application displays each document's filename, page count, and location.

Duplicate file paths are ignored.

### Step 2 — Arrange the Merge Order

Rearrange PDF documents using either:

- Dragging a file row to another position.
- Selecting a file and clicking **Move Up** or **Move Down**.

Files are merged in the order shown in the list.

### Step 3 — Choose Verification Settings

The option **Verify the appearance of every page after merging** is enabled by default.

Keeping this option enabled provides additional assurance that source pages and merged pages render identically under the verification settings.

For large documents, verification may take additional time.

### Step 4 — Start Merging

Click **START MERGE**.

Choose the destination and filename for the merged PDF.

The application begins processing in the background.

### Step 5 — Review the Result

Once processing finishes, PDF Stitcher displays a completion message containing the total merged page count and output location.

If an error occurs, the application reports the failure without publishing the incomplete temporary result.

## Project Structure

```text
PDF-Stitcher/
|
|-- pdf_stitcher.py
|-- requirements.txt
|-- .gitignore
|-- README.md
```

**File descriptions:**

- `pdf_stitcher.py` — Main application, GUI, PDF merging logic, integrity checks, and verification.
- `requirements.txt` — Python package dependencies.
- `.gitignore` — Excludes unnecessary development and temporary files.
- `README.md` — Project documentation.

## Safety and Reliability

PDF Stitcher includes several measures intended to prevent incomplete or unexpected output.

### Source Validation

Before adding a document, the application checks whether:

- The file can be opened as a PDF.
- The document requires a password.
- The document contains at least one page.
- PyMuPDF reports that the document required repair.

### Source Change Detection

The application records each source file's size and modification timestamp.

These values are checked again during processing to detect files that have changed since they were added.

### Temporary Output

The merged document is initially written to a temporary file in the destination directory.

The final output is published using `os.replace()` only after the required checks succeed.

This helps prevent an incomplete merge from replacing an existing output file.

### Background Execution

Merging runs on a worker thread, while the main Tkinter event loop handles interface updates.

This prevents the main interface from being blocked by the merge operation.

## Limitations

- Password-protected PDFs must be unlocked before adding them.
- PDFs that require repair are rejected during initial inspection.
- The application merges entire documents; it does not currently support selecting individual pages or page ranges.
- Visual verification renders pages at 72 DPI and does not guarantee preservation of every PDF feature.
- PDF outlines, document-level metadata, digital signatures, and certain interactive behaviors may not be preserved as originally authored.
- Large PDF collections can require substantial processing time and memory, particularly when verification is enabled.
- The application does not currently provide PDF compression presets, page editing, OCR, or encryption tools.
- Automated cross-platform compatibility testing has not been documented.

## Future Improvements

Potential enhancements include:

- Individual page selection and page-range merging
- PDF preview thumbnails
- Page rotation and deletion
- Bookmark and outline preservation
- More detailed verification reports
- Batch merge presets
- PDF metadata management
- Optional PDF compression
- Standalone executable packaging
- Automated testing for complex PDF documents

## Privacy

PDF Stitcher processes files locally using PyMuPDF.

The current implementation does not upload documents to a server or require an online account.

## Author

**Mridul Mayank Jha**

B.Tech — Computer Science and Engineering  
Sikkim Manipal Institute of Technology

GitHub: [Apple-Head20](https://github.com/Apple-Head20)

Repository: [PDF-Stitcher](https://github.com/Apple-Head20/PDF-Stitcher)

---

**PDF Stitcher — Merge documents. Preserve pages. Verify results.**
