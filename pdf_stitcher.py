"""PDF Stitcher - a native-page PDF merger with a Tkinter GUI.

Requirements: pip install pymupdf
Run: python pdf_stitcher.py

This tool copies PDF pages without rasterizing them. It validates the merged
page count and, by default, renders every source/merged page for comparison.
"""

from __future__ import annotations

import os
import queue
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    import fitz  # PyMuPDF
except ImportError:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "PyMuPDF is missing",
        "Install the PDF library first:\n\npython -m pip install pymupdf",
    )
    root.destroy()
    sys.exit(1)


@dataclass(frozen=True)
class InputPDF:
    path: Path
    pages: int
    size: int
    modified_ns: int


def inspect_pdf(path: Path) -> InputPDF:
    info = path.stat()
    with fitz.open(str(path)) as document:
        if not document.is_pdf:
            raise ValueError("This is not a PDF document.")
        if document.needs_pass:
            raise ValueError("This PDF requires a password. Unlock it before adding.")
        if document.page_count < 1:
            raise ValueError("This PDF has no pages.")
        if document.is_repaired:
            raise ValueError("This PDF seems damaged and requires repair. Refusing to merge silently.")
        count = document.page_count
    return InputPDF(path, count, info.st_size, info.st_mtime_ns)


def check_unchanged(item: InputPDF) -> None:
    info = item.path.stat()
    if info.st_size != item.size or info.st_mtime_ns != item.modified_ns:
        raise RuntimeError(
            f"Source file changed since it was added. Please remove and re-add it:\n{item.path}"
        )


def merge_pdfs(items: list[InputPDF], destination: Path, verify_visuals: bool, events: queue.Queue) -> None:
    """Merge on a worker thread, then atomically publish the verified output."""
    temp_path = None
    count = sum(item.pages for item in items)
    total_steps = len(items) + (count if verify_visuals else 0)
    try:
        # Save next to final output so that replacement stays on the same drive.
        fd, name = tempfile.mkstemp(prefix="._pdf_stitcher_", suffix=".pdf", dir=str(destination.parent))
        os.close(fd)
        temp_path = Path(name)

        with fitz.open() as merged:
            for index, item in enumerate(items, 1):
                check_unchanged(item)
                events.put(("status", f"Merging {index}/{len(items)}: {item.path.name}"))
                with fitz.open(str(item.path)) as source:
                    if source.needs_pass or source.page_count != item.pages or source.is_repaired:
                        raise RuntimeError(f"Source PDF is now unreadable or has changed: {item.path}")
                    # Insert all pages. Text, vectors, images and annotations remain PDF data.
                    merged.insert_pdf(
                        source,
                        from_page=0,
                        to_page=source.page_count - 1,
                        links=True,
                        annots=True,
                        widgets=True,
                        join_duplicates=False,
                    )
                events.put(("progress", index, total_steps))

            if merged.page_count != count:
                raise RuntimeError(f"Page-count mismatch during merge: expected {count}, got {merged.page_count}.")

            # Compression is lossless; no JPEG conversions, page resizing or new pages.
            merged.save(str(temp_path), garbage=3, deflate=True)

        with fitz.open(str(temp_path)) as result:
            if result.page_count != count:
                raise RuntimeError(
                    f"Output has {result.page_count} pages; expected {count}. No file was published."
                )

            if verify_visuals:
                position = 0
                # Render at 72 dpi. Checks every single page, including diagrams/images.
                # Native text and graphics are NOT replaced by these verification images.
                for file_index, item in enumerate(items, 1):
                    check_unchanged(item)
                    events.put(("status", f"Verifying pages in {file_index}/{len(items)}: {item.path.name}"))
                    with fitz.open(str(item.path)) as source:
                        for page_index in range(item.pages):
                            original_page = source[page_index]
                            copied_page = result[position]
                            # Compare the extractable text layer as well as the appearance.
                            if original_page.get_text("text") != copied_page.get_text("text"):
                                raise RuntimeError(
                                    f"Text verification failed in '{item.path.name}', "
                                    f"page {page_index + 1}. No file was published."
                                )
                            original = original_page.get_pixmap(
                                matrix=fitz.Matrix(1, 1), colorspace=fitz.csRGB, alpha=False, annots=True
                            )
                            copied = copied_page.get_pixmap(
                                matrix=fitz.Matrix(1, 1), colorspace=fitz.csRGB, alpha=False, annots=True
                            )
                            if (original.width, original.height, original.digest) != (
                                copied.width, copied.height, copied.digest
                            ):
                                raise RuntimeError(
                                    "Visual verification failed. The merged result does not match "
                                    f"'{item.path.name}', page {page_index + 1}. "
                                    "No file was published."
                                )
                            position += 1
                            if position % 5 == 0 or position == count:
                                events.put(("progress", len(items) + position, total_steps))
                if position != count:
                    raise RuntimeError("Verification did not cover the expected number of pages.")

        # The old output is never truncated before the new PDF passes verification.
        for item in items:
            check_unchanged(item)
        os.replace(str(temp_path), str(destination))
        temp_path = None
        events.put(("done", str(destination), count))
    except Exception as exc:
        events.put(("error", str(exc)))
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


class PDFStitcherApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("PDF Stitcher — Merge without altering pages")
        self.root.geometry("1020x640")
        self.root.minsize(780, 490)
        self.files: list[InputPDF] = []
        self.busy = False
        self.drag_from: int | None = None
        self.events: queue.Queue = queue.Queue()
        self.verify_var = tk.BooleanVar(value=True)
        self.summary_var = tk.StringVar(value="No PDFs added")
        self.status_var = tk.StringVar(value="Add PDFs, arrange their order, then press Start Merge.")

        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("Sub.TLabel", font=("Segoe UI", 10))
        style.configure("Treeview", rowheight=27, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
        style.configure("Start.TButton", font=("Segoe UI", 11, "bold"), padding=(16, 10))

        content = ttk.Frame(root, padding=18)
        content.pack(fill="both", expand=True)

        ttk.Label(content, text="PDF Stitcher", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            content,
            text="20+ PDF files supported • original page order and quality retained • no extra pages",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(4, 14))

        toolbar = ttk.Frame(content)
        toolbar.pack(fill="x", pady=(0, 10))
        self.controls: list[ttk.Button] = []

        def tool(label: str, fn) -> None:
            button = ttk.Button(toolbar, text=label, command=fn)
            button.pack(side="left", padx=(0, 8))
            self.controls.append(button)

        tool("+ Add PDFs", self.add_files)
        tool("Remove selected", self.remove_selected)
        tool("Move up ↑", lambda: self.move_selected(-1))
        tool("Move down ↓", lambda: self.move_selected(1))
        tool("Clear all", self.clear_all)

        table_frame = ttk.Frame(content)
        table_frame.pack(fill="both", expand=True)
        self.table = ttk.Treeview(
            table_frame,
            columns=("order", "name", "pages", "location"),
            show="headings",
            selectmode="extended",
        )
        self.table.heading("order", text="#")
        self.table.heading("name", text="PDF file")
        self.table.heading("pages", text="Pages")
        self.table.heading("location", text="Folder")
        self.table.column("order", width=52, anchor="center", stretch=False)
        self.table.column("name", width=280, minwidth=130)
        self.table.column("pages", width=75, anchor="center", stretch=False)
        self.table.column("location", width=430, minwidth=140)
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.table.bind("<ButtonPress-1>", self.begin_drag, add="+")
        self.table.bind("<ButtonRelease-1>", self.end_drag, add="+")
        self.table.bind("<Delete>", lambda _: self.remove_selected())
        root.bind("<Control-o>", lambda _: self.add_files())

        bottom = ttk.Frame(content)
        bottom.pack(fill="x", pady=(10, 0))
        ttk.Label(bottom, textvariable=self.summary_var, font=("Segoe UI", 10, "bold")).pack(side="left")
        ttk.Label(bottom, text="Drag a row to reorder; or select rows and use ↑ / ↓.").pack(side="right")

        options = ttk.Frame(content)
        options.pack(fill="x", pady=(12, 8))
        self.check = ttk.Checkbutton(
            options,
            text="Verify the appearance of every page after merging (recommended, slower)",
            variable=self.verify_var,
        )
        self.check.pack(anchor="w")

        self.progress = ttk.Progressbar(content, mode="determinate")
        self.progress.pack(fill="x", pady=(5, 7))
        ttk.Label(content, textvariable=self.status_var, wraplength=960).pack(anchor="w", pady=(0, 10))

        self.start_button = ttk.Button(content, text="START MERGE", style="Start.TButton", command=self.start)
        self.start_button.pack(fill="x")
        self.refresh()
        self.root.after(80, self.process_events)

    def refresh(self, selected: set[int] | None = None) -> None:
        self.table.delete(*self.table.get_children())
        for index, item in enumerate(self.files):
            self.table.insert(
                "", "end", iid=str(index),
                values=(index + 1, item.path.name, item.pages, str(item.path.parent)),
            )
        if selected:
            valid = [str(index) for index in sorted(selected) if index < len(self.files)]
            self.table.selection_set(valid)
            if valid:
                self.table.see(valid[0])
        self.summary_var.set(f"{len(self.files)} PDFs  |  {sum(item.pages for item in self.files)} total pages")
        self.start_button.configure(state="normal" if self.files and not self.busy else "disabled")

    def selected_indices(self) -> set[int]:
        return {int(key) for key in self.table.selection()}

    def add_files(self) -> None:
        if self.busy:
            return
        names = filedialog.askopenfilenames(
            title="Choose PDF files (select as many as you want)",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        existing = {os.path.normcase(str(item.path)) for item in self.files}
        failures: list[str] = []
        additions = 0
        for name in names:
            path = Path(name).resolve()
            key = os.path.normcase(str(path))
            if key in existing:
                continue
            try:
                item = inspect_pdf(path)
                self.files.append(item)
                existing.add(key)
                additions += 1
            except Exception as exc:
                failures.append(f"{path.name}: {exc}")
        self.refresh()
        self.status_var.set(f"Added {additions} PDF(s). Arrange them before you start.")
        if failures:
            messagebox.showwarning("Some PDFs could not be added", "\n\n".join(failures[:12]))

    def remove_selected(self) -> None:
        if self.busy:
            return
        selected = self.selected_indices()
        if selected:
            self.files = [item for index, item in enumerate(self.files) if index not in selected]
            self.refresh()

    def clear_all(self) -> None:
        if self.busy:
            return
        self.files.clear()
        self.refresh()
        self.status_var.set("List cleared. Add new PDFs to begin.")

    def move_selected(self, direction: int) -> None:
        if self.busy:
            return
        selected = self.selected_indices()
        if not selected:
            return
        order = range(1, len(self.files)) if direction == -1 else range(len(self.files) - 2, -1, -1)
        for index in order:
            moving = index if direction == -1 else index + 1
            neighbor = moving + direction
            if moving in selected and neighbor not in selected:
                self.files[moving], self.files[neighbor] = self.files[neighbor], self.files[moving]
                selected.remove(moving)
                selected.add(neighbor)
        self.refresh(selected)

    def begin_drag(self, event) -> None:
        if self.busy:
            return
        row = self.table.identify_row(event.y)
        self.drag_from = int(row) if row else None

    def end_drag(self, event) -> None:
        if self.busy or self.drag_from is None:
            return
        row = self.table.identify_row(event.y)
        start = self.drag_from
        self.drag_from = None
        if not row:
            return
        target = int(row)
        if start == target:
            return
        moved = self.files.pop(start)
        self.files.insert(target, moved)
        self.refresh({target})

    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        state = "disabled" if busy else "normal"
        for button in self.controls:
            button.configure(state=state)
        self.check.configure(state=state)
        self.refresh()

    def start(self) -> None:
        if self.busy or not self.files:
            return
        target_name = filedialog.asksaveasfilename(
            title="Save merged PDF as",
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            initialdir=str(self.files[0].path.parent),
            initialfile="merged.pdf",
        )
        if not target_name:
            return
        target = Path(target_name).resolve()
        if any(os.path.normcase(str(item.path)) == os.path.normcase(str(target)) for item in self.files):
            messagebox.showerror("Invalid output", "Output file cannot be one of the input PDFs.")
            return
        if target.exists() and not messagebox.askyesno(
            "Replace existing output?", f"An output already exists:\n\n{target}\n\nReplace it after verification?"
        ):
            return

        self.progress.configure(value=0, maximum=len(self.files) + (sum(x.pages for x in self.files) if self.verify_var.get() else 0))
        self.set_busy(True)
        self.status_var.set("Starting merge…")
        worker = threading.Thread(
            target=merge_pdfs,
            args=(list(self.files), target, self.verify_var.get(), self.events),
            daemon=True,
        )
        worker.start()

    def process_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "status":
                    self.status_var.set(event[1])
                elif kind == "progress":
                    self.progress.configure(value=event[1], maximum=event[2])
                elif kind == "done":
                    _, file_path, count = event
                    self.set_busy(False)
                    self.status_var.set(f"Complete: {count} pages merged and saved to {file_path}")
                    messagebox.showinfo("Merge complete", f"Successfully merged {len(self.files)} PDFs ({count} pages).\n\nSaved to:\n{file_path}")
                elif kind == "error":
                    self.set_busy(False)
                    self.status_var.set("Merge failed. No new output was published.")
                    messagebox.showerror("Merge failed", event[1])
        except queue.Empty:
            pass
        self.root.after(80, self.process_events)


if __name__ == "__main__":
    app_root = tk.Tk()
    PDFStitcherApp(app_root)
    app_root.mainloop()
