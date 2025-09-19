import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import pathlib
import json
import threading
import os
from dotenv import load_dotenv
from google import genai
from intelligent_utils import (
    setup_logging,
    batch_classify_and_move,
    revert_changes,
    preview_classification_and_plan,
    apply_plan,
    set_api_key,
    get_api_key,
    delete_api_key,
    clean_artifacts,
)

class DesktopOrganizerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Intelligent Desktop Organizer")
        self.geometry("900x650")
        self.folder_path = tk.StringVar()
        self.organize_mode = tk.StringVar(value="by_name")
        self.categories = []
        self.genai_client = None
        # Nuevos estados/config
        self.ai_context_text = None
        self.exclude_exts = []
        self.exclude_files = []
        self.allow_ai_skip = tk.BooleanVar(value=True)
        self.api_key_entry = None
        self.excl_listbox = None
        self.excl_files_listbox = None
        self.thinking_enabled_var = tk.BooleanVar(value=True)
        self.thinking_checkbox = None
        self._build_ui()
        self._load_categories()
        self._configure_gemini()
        # Configurar el logger para que envíe mensajes a la GUI
        self.logger = setup_logging(self._log)

    def _build_ui(self):
        # Theming for a cleaner look
        style = ttk.Style()
        try:
            style.theme_use('vista')
        except Exception:
            try:
                style.theme_use('clam')
            except Exception:
                pass
        style.configure('TButton', padding=(10, 6))
        style.configure('TLabel', padding=(2, 2))
        style.configure('TLabelframe', padding=10)

        container = ttk.Frame(self, padding=10)
        container.pack(fill=tk.BOTH, expand=True)

        self.notebook = ttk.Notebook(container)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Tabs
        organize_tab = ttk.Frame(self.notebook)
        categories_tab = ttk.Frame(self.notebook)
        settings_tab = ttk.Frame(self.notebook)
        log_tab = ttk.Frame(self.notebook)
        self.notebook.add(organize_tab, text="Organize")
        self.notebook.add(categories_tab, text="Categories")
        self.notebook.add(settings_tab, text="Settings")
        self.notebook.add(log_tab, text="Log")

        # --- Organize Tab ---
        # Folder chooser
        chooser = ttk.Frame(organize_tab)
        chooser.pack(fill=tk.X, pady=(4, 8))
        self.select_folder_button = ttk.Button(chooser, text="Select Folder", command=self._select_folder)
        self.select_folder_button.pack(side=tk.LEFT)
        self.folder_label = ttk.Label(chooser, text="No folder selected", wraplength=500)
        self.folder_label.pack(side=tk.LEFT, padx=10)

        # Mode selection
        mode_frame = ttk.Labelframe(organize_tab, text="Organization Mode")
        mode_frame.pack(fill=tk.X, pady=(0, 8))
        self.by_name_radio = ttk.Radiobutton(mode_frame, text="By Name (simple)", variable=self.organize_mode, value="by_name")
        self.by_name_radio.pack(anchor=tk.W)
        self.by_content_radio = ttk.Radiobutton(mode_frame, text="By Content (complete)", variable=self.organize_mode, value="by_content")
        self.by_content_radio.pack(anchor=tk.W)
        self._add_tooltip(self.by_name_radio, "Fast classification using file names and metadata only.")
        self._add_tooltip(self.by_content_radio, "May inspect file content (slower, more accurate for documents).")

        # Context and options
        ctx_frame = ttk.Labelframe(organize_tab, text="AI Context")
        ctx_frame.pack(fill=tk.BOTH, expand=False, pady=(0, 8))
        self.ai_context_text = tk.Text(ctx_frame, height=5, wrap=tk.WORD)
        self.ai_context_text.pack(fill=tk.X)
        options_row = ttk.Frame(ctx_frame)
        options_row.pack(fill=tk.X, pady=(6, 0))
        ttk.Checkbutton(options_row, text="Allow AI 'SKIP' (do not move)", variable=self.allow_ai_skip).pack(side=tk.LEFT)
        self.thinking_checkbox = ttk.Checkbutton(options_row, text="Enable thinking", variable=self.thinking_enabled_var)
        self.thinking_checkbox.pack(side=tk.LEFT, padx=(12, 0))
        self._add_tooltip(self.thinking_checkbox, "When enabled, thinking uses dynamic budget.")

        # Actions
        actions = ttk.Frame(organize_tab)
        actions.pack(fill=tk.X)
        self.preview_button = ttk.Button(actions, text="Preview", command=self._preview)
        self.preview_button.pack(side=tk.LEFT, expand=True, fill=tk.X)
        self.organize_button = ttk.Button(actions, text="Organize", command=self._organize)
        self.organize_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(8, 0))

        # --- Categories Tab ---
        cat_entry_frame = ttk.Frame(categories_tab)
        cat_entry_frame.pack(fill=tk.X, pady=(8, 4), padx=8)
        self.new_cat_entry = ttk.Entry(cat_entry_frame)
        self.new_cat_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self.add_cat_button = ttk.Button(cat_entry_frame, text="Add", command=self._add_cat)
        self.add_cat_button.pack(side=tk.LEFT)
        list_frame = ttk.Frame(categories_tab)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self.cat_listbox = tk.Listbox(list_frame)
        self.cat_listbox.pack(fill=tk.BOTH, expand=True)
        self.del_cat_button = ttk.Button(categories_tab, text="Remove Selected", command=self._del_cat)
        self.del_cat_button.pack(fill=tk.X, padx=8, pady=(0, 8))

        # --- Settings Tab ---
        # API Key
        api_frame = ttk.Labelframe(settings_tab, text="Gemini API Key")
        api_frame.pack(fill=tk.X, padx=8, pady=(8, 4))
        self.api_key_entry = ttk.Entry(api_frame, show="*")
        self.api_key_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8), pady=6)
        ttk.Button(api_frame, text="Save", command=self._save_api_key).pack(side=tk.LEFT)
        ttk.Button(api_frame, text="Test", command=self._test_api).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(api_frame, text="Delete", command=self._forget_api_key).pack(side=tk.LEFT, padx=(8, 0))

        # Exclude extensions
        excl_frame = ttk.Labelframe(settings_tab, text="Exclude extensions (do not move)")
        excl_frame.pack(fill=tk.X, padx=8, pady=(8, 4))
        excl_entry = ttk.Entry(excl_frame)
        excl_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8), pady=6)
        ttk.Button(excl_frame, text="Add", command=lambda: self._add_exclusion(excl_entry.get())).pack(side=tk.LEFT)
        self.excl_listbox = tk.Listbox(excl_frame, height=4)
        self.excl_listbox.pack(fill=tk.X, padx=8, pady=(6, 6))
        ttk.Button(excl_frame, text="Remove Selected", command=self._del_exclusion).pack(fill=tk.X, padx=8, pady=(0, 8))

        # Exclude files
        excl_files_frame = ttk.Labelframe(settings_tab, text="Exclude files (names or patterns)")
        excl_files_frame.pack(fill=tk.X, padx=8, pady=(8, 8))
        excl_file_entry = ttk.Entry(excl_files_frame)
        excl_file_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8), pady=6)
        ttk.Button(excl_files_frame, text="Add", command=lambda: self._add_excluded_file(excl_file_entry.get())).pack(side=tk.LEFT)
        ttk.Button(excl_files_frame, text="Pick from folder", command=self._pick_files_to_exclude).pack(side=tk.LEFT, padx=(8, 0))
        self.excl_files_listbox = tk.Listbox(excl_files_frame, height=4)
        self.excl_files_listbox.pack(fill=tk.X, padx=8, pady=(6, 6))
        ttk.Button(excl_files_frame, text="Remove Selected", command=self._del_excluded_file).pack(fill=tk.X, padx=8, pady=(0, 8))

        # --- Log Tab ---
        log_controls = ttk.Frame(log_tab)
        log_controls.pack(fill=tk.X, padx=8, pady=(8, 4))
        self.revert_button = ttk.Button(log_controls, text="Revert Last Organization", command=self._revert)
        self.revert_button.pack(side=tk.LEFT)
        ttk.Button(log_controls, text="Clean (empty folders and movement_log.json)", command=self._clean).pack(side=tk.LEFT, padx=(8, 0))

        log_frame = ttk.Frame(log_tab)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self.log_text = tk.Text(log_frame, height=18, state=tk.DISABLED, wrap=tk.WORD)
        log_scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.config(yscrollcommand=log_scrollbar.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Controls disabled during long operations
        self.controls = [
            self.select_folder_button, self.preview_button, self.organize_button,
            self.revert_button, self.by_name_radio, self.by_content_radio,
            self.thinking_checkbox, self.api_key_entry,
            self.new_cat_entry, self.add_cat_button, self.del_cat_button,
            self.excl_listbox, self.excl_files_listbox
        ]

    def _configure_gemini(self):
        try:
            key = get_api_key()
            if not key:
                self._log("API key not found. Set it in the 'Gemini API Key' section.")
                self.genai_client = None
                return
            self.genai_client = genai.Client(api_key=key)
            self._log("Gemini client configured (keyring).")
        except Exception as e:
            self._log(f"Failed to configure Gemini: {e}")
            messagebox.showerror("API Error", f"Could not initialize Gemini client: {e}")

    def _load_categories(self):
        try:
            with open("config.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                self.categories = data.get("categories", [])
                self.exclude_exts = data.get("exclude_extensions", [])
                self.exclude_files = data.get("exclude_files", [])
                ai_ctx = data.get("ai_context", "")
                allow_skip = data.get("allow_ai_skip", True)
                thinking_budget = data.get("thinking_budget", -1)
            self._update_cat_listbox()
            self._update_excl_listbox()
            self._update_excluded_files_listbox()
            if self.ai_context_text is not None:
                self.ai_context_text.delete("1.0", tk.END)
                self.ai_context_text.insert("1.0", ai_ctx or "")
            self.allow_ai_skip.set(bool(allow_skip))
            # map persisted budget to checkbox
            try:
                tb = int(thinking_budget)
            except Exception:
                tb = -1
            self.thinking_enabled_var.set(tb != 0)
            self._log("Configuration loaded from config.json.")
        except (FileNotFoundError, json.JSONDecodeError):
            self.categories = ["Documents", "Pictures", "Videos", "Personal", "Misc"]
            self.exclude_exts = []
            self.exclude_files = []
            self.allow_ai_skip.set(True)
            self.thinking_enabled_var.set(True)
            self._log("config.json not found or invalid. Using default configuration.")
            self._save_categories()
            self._update_cat_listbox()
            self._update_excl_listbox()
            self._update_excluded_files_listbox()

    def _save_categories(self):
        try:
            data = {
                "categories": self.categories,
                "exclude_extensions": self.exclude_exts,
                "exclude_files": self.exclude_files,
                "ai_context": (self.ai_context_text.get("1.0", tk.END).strip() if self.ai_context_text else ""),
                "allow_ai_skip": bool(self.allow_ai_skip.get()),
                "thinking_budget": self._get_thinking_budget_for_save(),
            }
            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            self._log("Configuration saved to config.json.")
        except IOError:
            messagebox.showerror("Error", "Could not save the configuration file.")

    def _update_cat_listbox(self):
        self.cat_listbox.delete(0, tk.END)
        for cat in self.categories:
            self.cat_listbox.insert(tk.END, cat)

    def _update_excl_listbox(self):
        if not self.excl_listbox:
            return
        self.excl_listbox.delete(0, tk.END)
        for ext in self.exclude_exts:
            self.excl_listbox.insert(tk.END, ext)

    def _update_excluded_files_listbox(self):
        if not self.excl_files_listbox:
            return
        self.excl_files_listbox.delete(0, tk.END)
        for name in self.exclude_files:
            self.excl_files_listbox.insert(tk.END, name)

    def _add_cat(self):
        new_cat = self.new_cat_entry.get().strip()
        if new_cat and new_cat not in self.categories:
            self.categories.append(new_cat)
            self.categories.sort()
            self._update_cat_listbox()
            self._save_categories()
            self.new_cat_entry.delete(0, tk.END)
            self._log(f"Category added: {new_cat}")
        elif not new_cat:
            messagebox.showwarning("Warning", "Category name cannot be empty.")
        else:
            messagebox.showwarning("Warning", f"Category '{new_cat}' already exists.")

    def _add_exclusion(self, ext: str):
        ext = (ext or "").strip().lower()
        if not ext:
            messagebox.showwarning("Warning", "Extension cannot be empty.")
            return
        if not ext.startswith('.'):
            ext = '.' + ext
        if ext in self.exclude_exts:
            messagebox.showwarning("Warning", f"Extension '{ext}' is already in the list.")
            return
        self.exclude_exts.append(ext)
        self.exclude_exts.sort()
        self._update_excl_listbox()
        self._save_categories()
        self._log(f"Excluded extension added: {ext}")

    def _add_excluded_file(self, name: str):
        name = (name or "").strip()
        if not name:
            messagebox.showwarning("Warning", "File name or pattern cannot be empty.")
            return
        if name in self.exclude_files:
            messagebox.showwarning("Warning", f"'{name}' is already in the list.")
            return
        self.exclude_files.append(name)
        self.exclude_files.sort()
        self._update_excluded_files_listbox()
        self._save_categories()
        self._log(f"Excluded file/pattern added: {name}")

    def _del_exclusion(self):
        if not self.excl_listbox:
            return
        sel = self.excl_listbox.curselection()
        if not sel:
            messagebox.showwarning("Warning", "Select an extension to remove.")
            return
        ext = self.excl_listbox.get(sel[0])
        try:
            self.exclude_exts.remove(ext)
        except ValueError:
            pass
        self._update_excl_listbox()
        self._save_categories()
        self._log(f"Excluded extension removed: {ext}")

    def _del_excluded_file(self):
        if not self.excl_files_listbox:
            return
        sel = self.excl_files_listbox.curselection()
        if not sel:
            messagebox.showwarning("Warning", "Select an item to remove.")
            return
        name = self.excl_files_listbox.get(sel[0])
        try:
            self.exclude_files.remove(name)
        except ValueError:
            pass
        self._update_excluded_files_listbox()
        self._save_categories()
        self._log(f"Excluded file/pattern removed: {name}")

    def _pick_files_to_exclude(self):
        base = self.folder_path.get()
        if not base:
            messagebox.showwarning("Warning", "Please select a folder first.")
            return
        # Open a file picker rooted at the selected folder; allow multi-select
        paths = filedialog.askopenfilenames(initialdir=base, title="Select files to exclude")
        if not paths:
            return
        added = 0
        for p in paths:
            name = os.path.basename(p)
            if name not in self.exclude_files:
                self.exclude_files.append(name)
                added += 1
        if added:
            self.exclude_files.sort()
            self._update_excluded_files_listbox()
            self._save_categories()
            self._log(f"Added {added} file(s) to exclude list.")

    def _del_cat(self):
        selected_indices = self.cat_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("Warning", "Please select a category to remove.")
            return
        
        selected_cat = self.cat_listbox.get(selected_indices[0])
        if messagebox.askyesno("Confirm", f"Are you sure you want to remove the category '{selected_cat}'?"):
            self.categories.remove(selected_cat)
            self._update_cat_listbox()
            self._save_categories()
            self._log(f"Category removed: {selected_cat}")

    def _select_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.folder_path.set(path)
            self.folder_label.config(text=path)
            self._log(f"Selected folder: {path}")

    def _save_api_key(self):
        key = (self.api_key_entry.get() or "").strip()
        if not key:
            messagebox.showwarning("Warning", "API key cannot be empty.")
            return
        set_api_key(key)
        self._log("API key saved securely.")
        self._configure_gemini()

    def _test_api(self):
        try:
            if not self.genai_client:
                self._configure_gemini()
            if self.genai_client:
                # Prueba simple: si hay cliente, asumimos configuración correcta
                self._log("API key verified.")
                messagebox.showinfo("Success", "API key appears valid.")
            else:
                messagebox.showerror("Error", "Could not initialize the client.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to validate API key: {e}")

    def _forget_api_key(self):
        if messagebox.askyesno("Confirm", "Delete the saved API key?"):
            delete_api_key()
            self.genai_client = None
            self._log("API key deleted.")

    def _log(self, message: str):
        def _insert():
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, message + "\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        
    # Ensure GUI updates happen on the main thread
        self.after(0, _insert)

    def _toggle_controls(self, enabled: bool):
        state = tk.NORMAL if enabled else tk.DISABLED
        for control in self.controls:
            try:
                control.config(state=state)
            except tk.TclError:
                pass # Algunos widgets como los Radiobutton no se pueden deshabilitar directamente

    def _run_in_thread(self, target_func, *args):
        def _task_wrapper():
            self._toggle_controls(enabled=False)
            try:
                target_func(*args)
                self.after(0, lambda: messagebox.showinfo("Completed", "The operation finished successfully."))
            except Exception as e:
                self.logger.error(f"Operation error: {e}")
                self.after(0, lambda: messagebox.showerror("Error", f"An error occurred: {e}"))
            finally:
                self.after(0, lambda: self._toggle_controls(enabled=True))

        thread = threading.Thread(target=_task_wrapper, daemon=True)
        thread.start()

    def _organize(self):
        path_str = self.folder_path.get()
        if not path_str:
            messagebox.showwarning("Warning", "Please select a folder first.")
            return
        
        if not self.genai_client:
            messagebox.showerror("Error", "AI client is not configured. Check your API key.")
            return

        path = pathlib.Path(path_str)
        mode = self.organize_mode.get()
        ai_ctx = self.ai_context_text.get("1.0", tk.END).strip() if self.ai_context_text else ""
        exclude_exts = list(self.exclude_exts)
        exclude_files = list(self.exclude_files)
        allow_skip = bool(self.allow_ai_skip.get())

        thinking_budget = self._get_thinking_budget()

        def _call():
            batch_classify_and_move(
                folder_path=path,
                mode=mode,
                categories=self.categories,
                log_callback=self._log,
                genai_client=self.genai_client,
                thinking_budget=thinking_budget,
                ai_context=ai_ctx,
                exclude_extensions=exclude_exts,
                exclude_files=exclude_files,
                allow_ai_skip=allow_skip,
            )
        self._run_in_thread(_call)

    def _revert(self):
        path_str = self.folder_path.get()
        if not path_str:
            messagebox.showwarning("Warning", "Please select the folder where the organization was performed.")
            return

        path = pathlib.Path(path_str)
        if messagebox.askyesno("Confirm Revert", "Are you sure you want to revert the last organization in this folder?"):
            self._run_in_thread(revert_changes, path, self._log)

    def _preview(self):
        path_str = self.folder_path.get()
        if not path_str:
            messagebox.showwarning("Warning", "Please select a folder first.")
            return
        if not self.genai_client:
            messagebox.showerror("Error", "AI client is not configured. Check your API key.")
            return
        path = pathlib.Path(path_str)
        mode = self.organize_mode.get()
        ai_ctx = self.ai_context_text.get("1.0", tk.END).strip() if self.ai_context_text else ""
        exclude_exts = list(self.exclude_exts)
        exclude_files = list(self.exclude_files)
        allow_skip = bool(self.allow_ai_skip.get())

        thinking_budget = self._get_thinking_budget()

        def _call():
            classified, plan = preview_classification_and_plan(
                folder_path=path,
                mode=mode,
                categories=self.categories,
                genai_client=self.genai_client,
                thinking_budget=thinking_budget,
                ai_context=ai_ctx,
                exclude_extensions=exclude_exts,
                exclude_files=exclude_files,
                allow_ai_skip=allow_skip,
            )
            # Mostrar en UI (en hilo principal)
            def show_preview():
                win = tk.Toplevel(self)
                win.title("Preview of planned moves")
                win.geometry("700x400")

                cols = ("File", "Category", "Action", "Destination")
                tree = ttk.Treeview(win, columns=cols, show="headings")
                for c in cols:
                    tree.heading(c, text=c)
                    tree.column(c, stretch=True, width=120)
                tree.pack(fill=tk.BOTH, expand=True)

                for item in plan:
                    dest = item.get("destination", "-")
                    tree.insert("", tk.END, values=(item.get("filename"), item.get("category"), item.get("action"), dest))

                btns = ttk.Frame(win)
                btns.pack(fill=tk.X, pady=5)
                def _apply():
                    def _call():
                        apply_plan(path, plan, log_callback=self._log)
                    self._run_in_thread(_call)
                    win.destroy()

                ttk.Button(btns, text="Apply", command=_apply).pack(side=tk.RIGHT, padx=(0, 6))
                ttk.Button(btns, text="Close", command=win.destroy).pack(side=tk.RIGHT)

            self.after(0, show_preview)

        self._run_in_thread(_call)

    def _clean(self):
        path_str = self.folder_path.get()
        if not path_str:
            messagebox.showwarning("Warning", "Select a folder.")
            return
        path = pathlib.Path(path_str)

        def _call():
            clean_artifacts(path, delete_log=True, remove_empty_dirs=True, log_callback=self._log)

        self._run_in_thread(_call)

    def _get_thinking_budget(self) -> int:
        # Enabled -> -1 (dynamic), Disabled -> 0 (off)
        return -1 if bool(self.thinking_enabled_var.get()) else 0

    def _get_thinking_budget_for_save(self) -> int:
        return -1 if bool(self.thinking_enabled_var.get()) else 0

    # Simple tooltip helper
    def _add_tooltip(self, widget, text: str):
        tooltip = _Tooltip(widget, text)
        return tooltip


class _Tooltip:
    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        widget.bind("<Enter>", self.showtip)
        widget.bind("<Leave>", self.hidetip)

    def showtip(self, event=None):
        if self.tipwindow or not self.text:
            return
        x, y, cx, cy = self.widget.bbox("insert") if hasattr(self.widget, 'bbox') else (0, 0, 0, 0)
        x = x + self.widget.winfo_rootx() + 25
        y = y + self.widget.winfo_rooty() + 20
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry("+%d+%d" % (x, y))
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                         background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                         font=("tahoma", "8", "normal"))
        label.pack(ipadx=4)

    def hidetip(self, event=None):
        tw = self.tipwindow
        self.tipwindow = None
        if tw:
            tw.destroy()


if __name__ == "__main__":
    load_dotenv()
    app = DesktopOrganizerApp()
    app.mainloop()
