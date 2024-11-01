import os
import json
import logging
import customtkinter as ctk
from tkinter import filedialog, messagebox, simpledialog
from typing import Dict, Any, Set, Optional, List
import threading
import time
import platform
import subprocess
import tkinter as tk

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    messagebox.showerror(
        "Missing Dependency",
        "The 'watchdog' library is required for file monitoring. Please install it using 'pip install watchdog'."
    )
    exit()

logging.basicConfig(level=logging.INFO)

# Configure default colors for light and dark mode
COLORS = {
    "light": {
        "text": "#1a1a1a",  # Darker text for better contrast in light mode
        "secondary_text": "#404040",  # Dark gray for secondary text
        "selected_bg": "#e6e6e6",  # Light gray for selected items
        "status_success": "#2d8a2d",  # Darker green for better visibility
        "status_warning": "#cc3300",  # Darker red for better visibility
        "folder_text": "#1a1a1a",  # Dark text for folder list
        "button_hover": "#d9d9d9",  # Light gray for button hover
    },
    "dark": {
        "text": "#ffffff",
        "secondary_text": "#d1d1d1",
        "selected_bg": "#404040",
        "status_success": "#33cc33",
        "status_warning": "#ff4d4d",
        "folder_text": "#ffffff",
        "button_hover": "#4d4d4d",
    }
}

class FileChangeHandler(FileSystemEventHandler):
    def __init__(self, app):
        super().__init__()
        self.app = app

    def on_any_event(self, event):
        # Schedule the files_changed update on the main thread
        self.app.root.after(0, self.app.set_files_changed)

class FileCollectorApp:
    def __init__(self, root: ctk.CTk) -> None:
        self.root = root
        self.root.title("File Collector App")
        
        # Load settings
        self.settings = self.load_settings()
        
        # Set appearance mode from settings
        ctk.set_appearance_mode(self.settings.get("theme", "System"))
        ctk.set_default_color_theme("blue")
        
        self.update_theme_colors()
        
        # Initialize variables
        self.projects: Dict[str, Dict[str, Any]] = {}
        self.presets: Dict[str, Dict[str, str]] = {}
        self.current_project: Optional[str] = None
        self.selected_folder_label: Optional[ctk.CTkLabel] = None
        self.auto_run_thread: Optional[threading.Thread] = None
        self.observer: Optional[Observer] = None
        self.files_changed: bool = False
        self.output_files: List[str] = []
        self.lock = threading.Lock()

        self.load_presets()
        self.load_projects()

        # Set up the GUI
        self.setup_gui()

        # Select the first project by default
        if self.projects:
            self.current_project = list(self.projects.keys())[0]
            self.update_project_list()
            self.create_main_content_widgets()
            
        # Bind theme change event
        self.root.bind("<<ThemeChanged>>", self.on_theme_change)

    def load_settings(self) -> Dict:
        if os.path.exists("settings.json"):
            try:
                with open("settings.json", "r") as f:
                    return json.load(f)
            except:
                return {"theme": "System"}
        return {"theme": "System"}

    def save_settings(self) -> None:
        try:
            with open("settings.json", "w") as f:
                json.dump(self.settings, f)
        except Exception as e:
            logging.error(f"Failed to save settings: {e}")

    def update_theme_colors(self):
        appearance_mode = ctk.get_appearance_mode().lower()
        self.colors = COLORS[appearance_mode]

    def on_theme_change(self, event=None):
        self.update_theme_colors()
        self.refresh_ui_colors()

    def toggle_theme(self):
        current_theme = ctk.get_appearance_mode()
        new_theme = "Light" if current_theme == "Dark" else "Dark"
        ctk.set_appearance_mode(new_theme)
        self.settings["theme"] = new_theme
        self.save_settings()
        self.update_theme_colors()
        self.refresh_ui_colors()

    def refresh_ui_colors(self):
        # Update colors for existing widgets
        if hasattr(self, 'sidebar_frame'):
            for widget in self.sidebar_frame.winfo_children():
                if isinstance(widget, ctk.CTkLabel):
                    widget.configure(text_color=self.colors["text"])
                elif isinstance(widget, ctk.CTkButton):
                    widget.configure(text_color=self.colors["text"])

        if hasattr(self, 'folder_list_frame'):
            for widget in self.folder_list_frame.winfo_children():
                widget.configure(text_color=self.colors["folder_text"])

        if hasattr(self, 'change_indicator'):
            if self.files_changed:
                self.change_indicator.configure(
                    text_color=self.colors["text"],
                    fg_color=self.colors["status_warning"]
                )
            else:
                self.change_indicator.configure(
                    text_color=self.colors["text"],
                    fg_color=self.colors["status_success"]
                )

    def setup_gui(self) -> None:
        # Configure root window
        self.root.geometry("900x600")

        # Create main frames with updated colors
        self.sidebar_frame = ctk.CTkFrame(self.root, width=200, corner_radius=0)
        self.sidebar_frame.pack(side="left", fill="y")

        self.main_frame = ctk.CTkFrame(self.root, corner_radius=0)
        self.main_frame.pack(side="right", fill="both", expand=True)

        # Theme switch in sidebar
        self.theme_switch = ctk.CTkButton(
            self.sidebar_frame,
            text="Toggle Theme",
            command=self.toggle_theme,
            width=160
        )
        self.theme_switch.pack(pady=10, padx=10)

        # Sidebar content
        self.setup_sidebar()

        # Main content area
        self.setup_main_content()

    def create_new_project(self) -> None:
        project_name = simpledialog.askstring("New Project", "Enter project name:")
        if project_name:
            if project_name in self.projects:
                messagebox.showerror("Error", "Project name already exists.")
                return
            self.projects[project_name] = {
                "folders": [],
                "ignore_folders": [],
                "ignore_filetypes": [],
                "ignore_filenames": [],
                "output_path": "",
                "max_file_size": 1024,
                "presets": [],
                "auto_run": False,
            }
            self.current_project = project_name
            self.save_projects_to_file()
            self.update_project_list()
            self.create_main_content_widgets()

    def setup_sidebar(self) -> None:
        # Sidebar Title
        sidebar_label = ctk.CTkLabel(
            self.sidebar_frame,
            text="Projects",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        sidebar_label.pack(pady=10)

        # Project List (Using CTkScrollableFrame)
        self.project_list_frame = ctk.CTkScrollableFrame(
            self.sidebar_frame, width=180, height=400
        )
        self.project_list_frame.pack(pady=5, padx=10, fill="both", expand=True)

        # Buttons
        self.new_project_btn = ctk.CTkButton(
            self.sidebar_frame, text="New Project", command=self.create_new_project
        )
        self.new_project_btn.pack(pady=5, padx=10, fill="x")

        self.delete_project_btn = ctk.CTkButton(
            self.sidebar_frame, text="Delete Project", command=self.delete_project
        )
        self.delete_project_btn.pack(pady=5, padx=10, fill="x")

        # Load projects into the list
        self.update_project_list()

    def delete_project(self) -> None:
        if not self.current_project:
            messagebox.showwarning("No Project", "Please select a project first.")
            return
        
        confirm = messagebox.askyesno(
            "Confirm Delete",
            f"Are you sure you want to delete project '{self.current_project}'?"
        )
        if confirm:
            del self.projects[self.current_project]
            self.save_projects_to_file()
            
            # Select a new current project if any exist
            if self.projects:
                self.current_project = list(self.projects.keys())[0]
            else:
                self.current_project = None
                
            self.update_project_list()
            self.create_main_content_widgets()

    def update_project_list(self) -> None:
        # Clear existing projects
        for widget in self.project_list_frame.winfo_children():
            widget.destroy()

        # Add projects to the list
        for project_name in sorted(self.projects.keys()):
            button = ctk.CTkButton(
                self.project_list_frame,
                text=project_name,
                command=lambda p=project_name: self.select_project(p),
                fg_color="transparent",
                text_color=self.colors["text"],
            )
            button.pack(fill="x", padx=5, pady=2)
            if project_name == self.current_project:
                button.configure(fg_color=self.colors["selected_bg"])

    def select_project(self, project_name: str) -> None:
        self.current_project = project_name
        self.update_project_list()
        self.create_main_content_widgets()
        self.load_project_settings()

    def setup_main_content(self) -> None:
        self.main_content_frame = ctk.CTkFrame(self.main_frame)
        self.main_content_frame.pack(fill="both", expand=True)
        self.create_main_content_widgets()

    def create_main_content_widgets(self) -> None:
        # Clear existing widgets
        for widget in self.main_content_frame.winfo_children():
            widget.destroy()

        if not self.current_project:
            label = ctk.CTkLabel(
                self.main_content_frame,
                text="Select a project from the sidebar or create a new one.",
                font=ctk.CTkFont(size=16),
            )
            label.pack(pady=20)
            return

        # Project Title
        project_label = ctk.CTkLabel(
            self.main_content_frame,
            text=f"Project: {self.current_project}",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        project_label.pack(pady=10)

        # Change Indicator
        self.change_indicator = ctk.CTkLabel(
            self.main_content_frame,
            text="Status: Up-to-date",
            fg_color=self.colors["status_success"],
            corner_radius=5,
            font=ctk.CTkFont(size=12),
            width=150,
            height=25,
        )
        self.change_indicator.pack(pady=5)

        # Tab Buttons
        tab_button_frame = ctk.CTkFrame(self.main_content_frame)
        tab_button_frame.pack(fill="x")

        self.tab_buttons = {}
        tabs = ["Folders", "Ignore Settings", "Output Settings", "Output Files"]
        for tab in tabs:
            btn = ctk.CTkButton(
                tab_button_frame,
                text=tab,
                command=lambda t=tab: self.show_tab(t),
                width=150,
                fg_color=("#3B8ED0", "#1F6AA5") if tab == "Folders" else "transparent",
            )
            btn.pack(side="left", padx=5, pady=5)
            self.tab_buttons[tab] = btn

        # Tab Frames
        self.tab_frames = {}
        self.folders_tab = ctk.CTkFrame(self.main_content_frame)
        self.ignore_tab = ctk.CTkFrame(self.main_content_frame)
        self.output_tab = ctk.CTkFrame(self.main_content_frame)
        self.output_files_tab = ctk.CTkFrame(self.main_content_frame)

        self.tab_frames["Folders"] = self.folders_tab
        self.tab_frames["Ignore Settings"] = self.ignore_tab
        self.tab_frames["Output Settings"] = self.output_tab
        self.tab_frames["Output Files"] = self.output_files_tab

        for frame in self.tab_frames.values():
            frame.pack(fill="both", expand=True)
            frame.pack_forget()

        # Initialize tabs
        self.setup_folders_tab()
        self.setup_ignore_tab()
        self.setup_output_tab()
        self.setup_output_files_tab()

        # Show default tab
        self.show_tab("Folders")

        # Action Buttons
        action_frame = ctk.CTkFrame(self.main_content_frame)
        action_frame.pack(pady=10)

        self.run_btn = ctk.CTkButton(
            action_frame, text="Run", command=self.run_file_collection, width=150
        )
        self.run_btn.pack(side="left", padx=20)

        self.open_output_btn = ctk.CTkButton(
            action_frame,
            text="Open Output Folder",
            command=self.open_output_folder,
            width=150,
        )
        self.open_output_btn.pack(side="left", padx=20)

        # Auto-run Toggle
        self.auto_run_var = ctk.BooleanVar(value=False)
        self.auto_run_checkbox = ctk.CTkCheckBox(
            self.main_content_frame,
            text="Auto-run on file changes",
            variable=self.auto_run_var,
            command=self.toggle_auto_run,
        )
        self.auto_run_checkbox.pack(pady=5)

        self.load_project_settings()
        self.start_file_monitoring()

    def load_project_settings(self) -> None:
        if not self.current_project:
            return
            
        project = self.projects[self.current_project]
        
        # Clear existing folders
        for widget in self.folder_list_frame.winfo_children():
            widget.destroy()

        # Load folders
        for folder in project.get("folders", []):
            self.add_folder_to_list(folder)

        # Load ignore settings
        self.ignore_folders_var.set(",".join(project.get("ignore_folders", [])))
        self.ignore_filetypes_var.set(",".join(project.get("ignore_filetypes", [])))
        self.ignore_filenames_var.set(",".join(project.get("ignore_filenames", [])))

        # Load output settings
        self.output_path_var.set(project.get("output_path", ""))
        self.max_file_size_var.set(str(project.get("max_file_size", 1024)))

        # Load auto-run setting
        self.auto_run_var.set(project.get("auto_run", False))

        # Load presets
        for preset_name, var in self.preset_vars.items():
            var.set(preset_name in project.get("presets", []))

        if self.auto_run_var.get():
            self.start_file_monitoring()

    def setup_folders_tab(self) -> None:
        # Folder List (Using CTkScrollableFrame)
        self.folder_list_frame = ctk.CTkScrollableFrame(self.folders_tab)
        self.folder_list_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Buttons
        folder_btn_frame = ctk.CTkFrame(self.folders_tab)
        folder_btn_frame.pack(pady=5)

        self.add_folder_btn = ctk.CTkButton(
            folder_btn_frame, text="Add Folder", command=self.add_folder, width=100
        )
        self.add_folder_btn.pack(side="left", padx=5)

        self.remove_folder_btn = ctk.CTkButton(
            folder_btn_frame, text="Remove Folder", command=self.remove_folder, width=100
        )
        self.remove_folder_btn.pack(side="right", padx=5)

    def setup_ignore_tab(self) -> None:
        ignore_label = ctk.CTkLabel(
            self.ignore_tab,
            text="Ignore Settings",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        ignore_label.pack(pady=10)

        # Ignore Folders
        self.ignore_folders_var = tk.StringVar()
        ctk.CTkLabel(self.ignore_tab, text="Folders:").pack(anchor="w", padx=10)
        self.ignore_folders_entry = ctk.CTkEntry(
            self.ignore_tab, textvariable=self.ignore_folders_var
        )
        self.ignore_folders_entry.pack(fill="x", padx=10, pady=5)
        self.ignore_folders_var.trace_add('write', lambda *args: self.save_project())

        # Ignore File Types
        self.ignore_filetypes_var = tk.StringVar()
        ctk.CTkLabel(self.ignore_tab, text="File Types:").pack(anchor="w", padx=10)
        self.ignore_filetypes_entry = ctk.CTkEntry(
            self.ignore_tab, textvariable=self.ignore_filetypes_var
        )
        self.ignore_filetypes_entry.pack(fill="x", padx=10, pady=5)
        self.ignore_filetypes_var.trace_add('write', lambda *args: self.save_project())

        # Ignore File Names
        self.ignore_filenames_var = tk.StringVar()
        ctk.CTkLabel(self.ignore_tab, text="File Names:").pack(anchor="w", padx=10)
        self.ignore_filenames_entry = ctk.CTkEntry(
            self.ignore_tab, textvariable=self.ignore_filenames_var
        )
        self.ignore_filenames_entry.pack(fill="x", padx=10, pady=5)
        self.ignore_filenames_var.trace_add('write', lambda *args: self.save_project())

        # Preset Selection
        ctk.CTkLabel(self.ignore_tab, text="Presets:").pack(anchor="w", padx=10, pady=5)
        self.preset_vars = {}
        self.preset_frame = ctk.CTkFrame(self.ignore_tab)
        self.preset_frame.pack(fill="x", padx=10, pady=5)
        for preset_name in self.presets.keys():
            var = tk.BooleanVar(value=False)
            cb = ctk.CTkCheckBox(
                self.preset_frame,
                text=preset_name,
                variable=var,
                command=self.update_ignore_settings_from_presets
            )
            cb.pack(anchor="w")
            self.preset_vars[preset_name] = var

    def setup_output_tab(self) -> None:
        output_label = ctk.CTkLabel(
            self.output_tab,
            text="Output Settings",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        output_label.pack(pady=10)

        # Output Path
        self.output_path_var = tk.StringVar()
        path_frame = ctk.CTkFrame(self.output_tab)
        path_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(path_frame, text="Output Path:").pack(side="left")
        self.output_path_entry = ctk.CTkEntry(
            path_frame, textvariable=self.output_path_var
        )
        self.output_path_entry.pack(side="left", fill="x", expand=True, padx=5)
        self.output_path_var.trace_add('write', lambda *args: self.save_project())
        self.output_path_btn = ctk.CTkButton(
            path_frame, text="Browse", command=self.select_output_path, width=80
        )
        self.output_path_btn.pack(side="right")

        # Max File Size
        self.max_file_size_var = tk.StringVar(value="1024")
        size_frame = ctk.CTkFrame(self.output_tab)
        size_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(size_frame, text="Max File Size (KB):").pack(side="left")
        self.max_file_size_entry = ctk.CTkEntry(
            size_frame, textvariable=self.max_file_size_var, width=100
        )
        self.max_file_size_entry.pack(side="left", padx=5)
        self.max_file_size_var.trace_add('write', lambda *args: self.save_project())

    def setup_output_files_tab(self) -> None:
        self.output_files_frame = ctk.CTkScrollableFrame(self.output_files_tab)
        self.output_files_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.update_output_files_tab()

    def update_output_files_tab(self) -> None:
        for widget in self.output_files_frame.winfo_children():
            widget.destroy()

        if not self.output_files:
            no_files_label = ctk.CTkLabel(
                self.output_files_frame, text="No output files generated yet."
            )
            no_files_label.pack(pady=10)
            return

        for file_path in self.output_files:
            file_frame = ctk.CTkFrame(self.output_files_frame)
            file_frame.pack(fill="x", padx=5, pady=5)

            file_label = ctk.CTkLabel(file_frame, text=file_path, anchor="w")
            file_label.pack(side="left", fill="x", expand=True)

            copy_path_btn = ctk.CTkButton(
                file_frame,
                text="Copy Path",
                command=lambda path=file_path: self.copy_to_clipboard(path),
                width=80,
            )
            copy_path_btn.pack(side="right", padx=5)

            copy_content_btn = ctk.CTkButton(
                file_frame,
                text="Copy Content",
                command=lambda path=file_path: self.copy_file_content(path),
                width=100,
            )
            copy_content_btn.pack(side="right", padx=5)

    def show_tab(self, tab_name: str) -> None:
        # Hide all frames
        for frame in self.tab_frames.values():
            frame.pack_forget()

        # Deselect all buttons
        for btn in self.tab_buttons.values():
            btn.configure(fg_color="transparent")

        # Show selected frame
        self.tab_frames[tab_name].pack(fill="both", expand=True)

        # Highlight selected button
        self.tab_buttons[tab_name].configure(fg_color=("#3B8ED0", "#1F6AA5"))

    def add_folder_to_list(self, folder_path: str) -> None:
        folder_label = ctk.CTkLabel(
            self.folder_list_frame,
            text=folder_path,
            anchor="w",
            width=400,
            text_color=self.colors["folder_text"]
        )
        folder_label.pack(fill="x", padx=5, pady=2)
        folder_label.bind("<Button-1>", lambda e: self.select_folder(folder_label))

    def select_folder(self, folder_label: ctk.CTkLabel) -> None:
        # Deselect all other labels
        for child in self.folder_list_frame.winfo_children():
            child.configure(fg_color="transparent")
        # Select this label
        folder_label.configure(fg_color=self.colors["selected_bg"])
        self.selected_folder_label = folder_label

    def add_folder(self) -> None:
        folder_path = filedialog.askdirectory()
        if folder_path:
            existing_folders = [
                child.cget("text") for child in self.folder_list_frame.winfo_children()
            ]
            if folder_path not in existing_folders:
                self.add_folder_to_list(folder_path)
                self.files_changed = True
                self.update_change_indicator()
                self.start_file_monitoring()
                self.save_project()
            else:
                messagebox.showinfo("Info", "Folder already added.")

    def remove_folder(self) -> None:
        if hasattr(self, "selected_folder_label") and self.selected_folder_label:
            self.selected_folder_label.destroy()
            self.selected_folder_label = None
            self.files_changed = True
            self.update_change_indicator()
            self.start_file_monitoring()
            self.save_project()
        else:
            messagebox.showwarning(
                "No Selection", "Please select a folder to remove."
            )

    def select_output_path(self) -> None:
        output_path = filedialog.askdirectory()
        if output_path:
            self.output_path_var.set(output_path)

    def update_ignore_settings_from_presets(self) -> None:
        ignore_folders = set()
        ignore_filetypes = set()
        ignore_filenames = set()

        # Add user's own entries
        user_ignore_folders = [x.strip() for x in self.ignore_folders_var.get().split(",") if x.strip()]
        user_ignore_filetypes = [x.strip() for x in self.ignore_filetypes_var.get().split(",") if x.strip()]
        user_ignore_filenames = [x.strip() for x in self.ignore_filenames_var.get().split(",") if x.strip()]

        ignore_folders.update(user_ignore_folders)
        ignore_filetypes.update(user_ignore_filetypes)
        ignore_filenames.update(user_ignore_filenames)

        # Add presets' entries
        selected_presets = []
        for preset_name, var in self.preset_vars.items():
            if var.get():
                selected_presets.append(preset_name)
                preset = self.presets.get(preset_name, {})
                ignore_folders.update([x.strip() for x in preset.get("ignore_folders", "").split(",") if x.strip()])
                ignore_filetypes.update([x.strip() for x in preset.get("ignore_filetypes", "").split(",") if x.strip()])
                ignore_filenames.update([x.strip() for x in preset.get("ignore_filenames", "").split(",") if x.strip()])

        # Update the StringVars
        self.ignore_folders_var.set(",".join(sorted(ignore_folders)))
        self.ignore_filetypes_var.set(",".join(sorted(ignore_filetypes)))
        self.ignore_filenames_var.set(",".join(sorted(ignore_filenames)))

        # Update selected presets in project and save
        if self.current_project and self.current_project in self.projects:
            self.projects[self.current_project]["presets"] = selected_presets
            self.save_projects_to_file()

    def toggle_auto_run(self) -> None:
        if self.auto_run_var.get():
            self.start_file_monitoring()
        else:
            self.stop_file_monitoring()
        self.save_project()

    def set_files_changed(self) -> None:
        with self.lock:
            self.files_changed = True
        self.update_change_indicator()

    def start_file_monitoring(self) -> None:
        self.stop_file_monitoring()
        if self.auto_run_var.get() and self.current_project:
            event_handler = FileChangeHandler(self)
            self.observer = Observer()
            folders = [child.cget("text") for child in self.folder_list_frame.winfo_children()]
            for folder in folders:
                if os.path.exists(folder):
                    self.observer.schedule(event_handler, path=folder, recursive=True)
            self.observer.start()
            # Start auto-run thread
            self.auto_run_thread = threading.Thread(target=self.auto_run_loop, daemon=True)
            self.auto_run_thread.start()

    def stop_file_monitoring(self) -> None:
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None

    def auto_run_loop(self) -> None:
        while self.auto_run_var.get():
            with self.lock:
                if self.files_changed:
                    self.files_changed = False
                    self.root.after(0, self.run_file_collection)
            time.sleep(1)

    def update_change_indicator(self) -> None:
        if self.files_changed:
            self.change_indicator.configure(
                text="Status: Changes detected",
                text_color=self.colors["text"],
                fg_color=self.colors["status_warning"],
            )
        else:
            self.change_indicator.configure(
                text="Status: Up-to-date",
                text_color=self.colors["text"],
                fg_color=self.colors["status_success"],
            )

    def open_output_folder(self) -> None:
        if not self.current_project:
            messagebox.showwarning("No Project", "Please select a project first.")
            return
        project = self.projects[self.current_project]
        output_path = project.get("output_path", "")
        output_folder_path = os.path.join(output_path, "outputs")
        if output_folder_path and os.path.exists(output_folder_path):
            if platform.system() == "Windows":
                os.startfile(output_folder_path)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", output_folder_path])
            else:
                subprocess.Popen(["xdg-open", output_folder_path])
        else:
            messagebox.showwarning("Invalid Path", "Output folder does not exist.")

    def save_project(self) -> None:
        if not self.current_project:
            return
        try:
            max_file_size = int(self.max_file_size_var.get())
        except ValueError:
            max_file_size = 1024  # Default value
        project = {
            "folders": [
                child.cget("text") for child in self.folder_list_frame.winfo_children()
            ],
            "ignore_folders": [
                x.strip()
                for x in self.ignore_folders_var.get().split(",")
                if x.strip()
            ],
            "ignore_filetypes": [
                x.strip()
                for x in self.ignore_filetypes_var.get().split(",")
                if x.strip()
            ],
            "ignore_filenames": [
                x.strip()
                for x in self.ignore_filenames_var.get().split(",")
                if x.strip()
            ],
            "output_path": self.output_path_var.get(),
            "max_file_size": max_file_size,
            "presets": [name for name, var in self.preset_vars.items() if var.get()],
            "auto_run": self.auto_run_var.get(),
        }
        self.projects[self.current_project] = project
        self.save_projects_to_file()

    def save_projects_to_file(self) -> None:
        try:
            with open("projects.json", "w") as f:
                json.dump(self.projects, f)
        except IOError as e:
            logging.error(f"Failed to save projects: {e}")
            messagebox.showerror("Error", "Failed to save projects.")

    def load_projects(self) -> None:
        if os.path.exists("projects.json"):
            try:
                with open("projects.json", "r") as f:
                    self.projects = json.load(f)
            except (IOError, json.JSONDecodeError) as e:
                logging.error(f"Failed to load projects.json: {e}")
                self.projects = {}
        else:
            self.projects = {}

    def load_presets(self) -> None:
        if os.path.exists("presets.json"):
            try:
                with open("presets.json", "r") as f:
                    self.presets = json.load(f)
            except (IOError, json.JSONDecodeError) as e:
                logging.error(f"Failed to load presets.json: {e}")
                self.presets = {"None": {}}
        else:
            # Default presets if the file doesn't exist
            self.presets = {
                "None": {
                    "ignore_folders": "",
                    "ignore_filetypes": "",
                    "ignore_filenames": "",
                }
            }

    def copy_to_clipboard(self, text: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        messagebox.showinfo("Copied", "Path copied to clipboard.")

    def copy_file_content(self, file_path: str) -> None:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            messagebox.showinfo("Copied", "File content copied to clipboard.")
        except Exception as e:
            logging.error(f"Failed to copy content: {e}")
            messagebox.showerror("Error", "Failed to copy file content.")

    def run_file_collection(self) -> None:
        if not self.current_project:
            self.root.after(0, lambda: messagebox.showerror("Error", "No project selected."))
            return

        project = self.projects[self.current_project]
        folders = [child.cget("text") for child in self.folder_list_frame.winfo_children()]
        ignore_folders: Set[str] = set(project["ignore_folders"])
        ignore_filetypes: Set[str] = set(project["ignore_filetypes"])
        ignore_filenames: Set[str] = set(project["ignore_filenames"])
        output_path = project["output_path"]
        max_file_size_kb = project.get("max_file_size", 1024)

        if not folders or not output_path:
            self.root.after(0, lambda: messagebox.showerror(
                "Error", "Folders or output path not specified."
            ))
            return

        output_folder_path = os.path.join(output_path, "outputs")
        os.makedirs(output_folder_path, exist_ok=True)

        collected_size = 0
        file_index = 1
        output_file_paths = []
        output_file_path = os.path.join(
            output_folder_path, f"{self.current_project}_output_{file_index}.txt"
        )
        output_file_paths.append(output_file_path)
        try:
            output_file = open(output_file_path, "w", encoding="utf-8")
            try:
                def write_content(content, header):
                    nonlocal collected_size, output_file, output_file_paths, file_index
                    total_content = f"{header}{content}\n\n"
                    total_content_bytes = total_content.encode('utf-8')
                    total_length = len(total_content_bytes)
                    start = 0
                    while start < total_length:
                        remaining_space_kb = max_file_size_kb - collected_size
                        if remaining_space_kb <= 0:
                            output_file.close()
                            file_index += 1
                            output_file_path = os.path.join(
                                output_folder_path, f"{self.current_project}_output_{file_index}.txt"
                            )
                            output_file_paths.append(output_file_path)
                            output_file = open(output_file_path, "w", encoding="utf-8")
                            collected_size = 0
                            remaining_space_kb = max_file_size_kb

                        remaining_space_bytes = int(remaining_space_kb * 1024)
                        end = start + remaining_space_bytes
                        chunk_bytes = total_content_bytes[start:end]
                        chunk = chunk_bytes.decode('utf-8', errors='ignore')
                        output_file.write(chunk)
                        chunk_size_kb = len(chunk_bytes) / 1024
                        collected_size += chunk_size_kb
                        start = end

                for root_folder in folders:
                    for root, dirs, files in os.walk(root_folder):
                        # Remove the output folder from dirs to prevent os.walk() from traversing it
                        dirs[:] = [d for d in dirs if os.path.join(root, d) != output_folder_path and d not in ignore_folders]
                        for file in files:
                            file_path = os.path.join(root, file)
                            file_ext = os.path.splitext(file)[1]
                            if (file in ignore_filenames) or (file_ext in ignore_filetypes):
                                continue
                            if file_path.startswith(output_folder_path):
                                continue
                            try:
                                with open(file_path, "r", encoding="utf-8") as f:
                                    content = f.read()
                                header = f"File: {file_path}\n"
                                write_content(content, header)
                            except Exception as e:
                                logging.warning(f"Failed to read {file_path}: {e}")
                output_file.close()
            except Exception as e:
                output_file.close()
                logging.error(f"Error during file collection: {e}")
                self.root.after(0, lambda: messagebox.showerror("Error", f"Error during file collection: {e}"))
                return
        except IOError as e:
            logging.error(f"Failed to open output file: {e}")
            self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to open output file: {e}"))
            return

        self.output_files = output_file_paths
        self.files_changed = False
        self.root.after(0, self.update_change_indicator)
        self.root.after(0, self.update_output_files_tab)
        # Update status label with timestamp
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        self.root.after(0, lambda: self.change_indicator.configure(
            text=f"Last run: {timestamp}",
            fg_color=self.colors["status_success"],
        ))

if __name__ == "__main__":
    root = ctk.CTk()
    app = FileCollectorApp(root)
    root.mainloop()
