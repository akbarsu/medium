import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from tkhtmlview import HTMLLabel
import markdown
import requests
import openai
import language_tool_python
import threading
import os
import time
import re
import queue

# pip install tkhtmlview markdown requests openai language_tool_python


class MediumPosterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Medium Poster")

        # Variables
        self.api_token = tk.StringVar()
        self.user_id = None
        self.openai_api_key = tk.StringVar()  # OpenAI API Key
        self.title = tk.StringVar()
        self.tags = tk.StringVar()
        self.canonical_url = tk.StringVar()
        self.publish_status = tk.StringVar(value="draft")
        self.notify_followers = tk.BooleanVar(value=False)
        self.license = tk.StringVar(value="all-rights-reserved")
        self.featured_image_path = None
        self.featured_image_url = tk.StringVar()
        self.current_file = None
        self.auto_save_interval = 30000  # Auto-save every 30 seconds
        self.auto_save_file = f"autosave_{os.getpid()}.md"
        self.tool = language_tool_python.LanguageTool('en-US')
        self.grammar_matches = []  # Store grammar matches

        # Grammar check debounce variables
        self.grammar_check_queue = queue.Queue()
        self.grammar_check_thread = None
        self.grammar_check_scheduled = False
        self.current_content_version = None  # For synchronization

        # Auto-save ID for cancelling
        self.auto_save_id = None

        # Status messages
        self.status_var = tk.StringVar()
        self.status_message = ""
        self.auto_save_message = ""
        self.update_status_bar()

        # Layout
        self.create_menu()
        self.create_widgets()

        # Start auto-save
        self.schedule_auto_save()

        # Check for auto-save file
        self.check_autosave()

    def create_widgets(self):
        # API Token Frame
        token_frame = ttk.Frame(self.root)
        token_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(token_frame, text="Medium API Token:").pack(side=tk.LEFT)
        ttk.Entry(token_frame, textvariable=self.api_token, show="*").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(token_frame, text="Set Token", command=self.get_user_id).pack(side=tk.LEFT)

        # OpenAI API Key Frame
        openai_frame = ttk.Frame(self.root)
        openai_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(openai_frame, text="OpenAI API Key:").pack(side=tk.LEFT)
        ttk.Entry(openai_frame, textvariable=self.openai_api_key, show="*").pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Title Frame with Generate Button
        title_frame = ttk.Frame(self.root)
        title_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(title_frame, text="Title:").pack(side=tk.LEFT)
        ttk.Entry(title_frame, textvariable=self.title).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(title_frame, text="Generate Title", command=self.generate_title).pack(side=tk.LEFT)

        # Tags Frame with Suggest Button
        tags_frame = ttk.Frame(self.root)
        tags_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(tags_frame, text="Tags (comma separated):").pack(side=tk.LEFT)
        ttk.Entry(tags_frame, textvariable=self.tags).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(tags_frame, text="Suggest Tags", command=self.suggest_tags).pack(side=tk.LEFT)

        # Canonical URL Frame
        canonical_frame = ttk.Frame(self.root)
        canonical_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(canonical_frame, text="Canonical URL:").pack(side=tk.LEFT)
        ttk.Entry(canonical_frame, textvariable=self.canonical_url).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Publish Options Frame
        options_frame = ttk.Frame(self.root)
        options_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(options_frame, text="Publish Status:").pack(side=tk.LEFT)
        publish_status_optionmenu = ttk.OptionMenu(
            options_frame,
            self.publish_status,
            self.publish_status.get(),
            "draft",
            "public",
            "unlisted",
        )
        publish_status_optionmenu.pack(side=tk.LEFT)

        ttk.Checkbutton(
            options_frame,
            text="Notify Followers",
            variable=self.notify_followers,
        ).pack(side=tk.LEFT)

        ttk.Label(options_frame, text="License:").pack(side=tk.LEFT)
        license_optionmenu = ttk.OptionMenu(
            options_frame,
            self.license,
            self.license.get(),
            "all-rights-reserved",
            "cc-40-by",
            "cc-40-by-sa",
            "cc-40-by-nd",
            "cc-40-by-nc",
            "cc-40-by-nc-nd",
            "cc-40-by-nc-sa",
            "cc-40-zero",
            "public-domain",
        )
        license_optionmenu.pack(side=tk.LEFT)

        # Featured Image Frame
        image_frame = ttk.Frame(self.root)
        image_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Button(
            image_frame,
            text="Select Featured Image",
            command=self.select_featured_image,
        ).pack(side=tk.LEFT)

        self.image_label = ttk.Label(image_frame, text="No image selected")
        self.image_label.pack(side=tk.LEFT)

        # Image URL Entry
        ttk.Label(image_frame, text="Or enter image URL:").pack(side=tk.LEFT)
        ttk.Entry(image_frame, textvariable=self.featured_image_url).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Content Frame
        content_frame = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Rich Text Editor with Syntax Highlighting
        self.content_text = scrolledtext.ScrolledText(content_frame, wrap=tk.WORD, undo=True)
        self.content_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.content_text.bind("<<Modified>>", self.on_content_modified)
        self.content_text.bind("<Button-3>", self.show_suggestions)  # Right-click for suggestions
        content_frame.add(self.content_text)

        # Preview Frame
        self.preview_html = HTMLLabel(content_frame, html="<p>Preview will appear here</p>")
        self.preview_html.pack(fill=tk.BOTH, expand=True)
        content_frame.add(self.preview_html)

        # Buttons Frame
        buttons_frame = ttk.Frame(self.root)
        buttons_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Button(buttons_frame, text="Post to Medium", command=self.post_to_medium).pack(side=tk.LEFT)
        ttk.Label(buttons_frame, text="Auto-save interval (sec):").pack(side=tk.LEFT)
        self.auto_save_entry = ttk.Entry(buttons_frame, width=5)
        self.auto_save_entry.insert(0, str(self.auto_save_interval // 1000))
        self.auto_save_entry.pack(side=tk.LEFT)
        ttk.Button(buttons_frame, text="Set Interval", command=self.set_auto_save_interval).pack(side=tk.LEFT)

        # Status Bar
        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self.status_bar = ttk.Label(status_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor='w')
        self.status_bar.pack(fill=tk.X, side=tk.LEFT, expand=True)

    def create_menu(self):
        menu_bar = tk.Menu(self.root)
        self.root.config(menu=menu_bar)

        # File menu
        file_menu = tk.Menu(menu_bar, tearoff=0)
        menu_bar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New", command=self.new_file, accelerator="Ctrl+N")
        file_menu.add_command(label="Open...", command=self.open_file, accelerator="Ctrl+O")
        file_menu.add_command(label="Save", command=self.save_file, accelerator="Ctrl+S")
        file_menu.add_command(label="Save As...", command=self.save_file_as)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_exit)

        # Bind shortcuts
        self.root.bind('<Control-n>', self.new_file)
        self.root.bind('<Control-o>', self.open_file)
        self.root.bind('<Control-s>', self.save_file)

    def select_featured_image(self):
        filetypes = [
            ("Image files", "*.png *.jpg *.jpeg *.gif"),
            ("All files", "*.*"),
        ]
        filename = filedialog.askopenfilename(
            title="Select Featured Image", filetypes=filetypes
        )
        if filename:
            self.featured_image_path = filename
            self.image_label.config(text=filename)
            # Reset featured image URL
            self.featured_image_url.set("")

    def on_content_modified(self, event=None):
        self.content_text.edit_modified(0)
        self.preview_content()
        self.highlight_syntax()
        self.current_content_version = time.time()  # Update content version
        self.debounce_grammar_check()

    def preview_content(self):
        markdown_text = self.content_text.get("1.0", tk.END)
        # If featured image URL is provided, insert it into the content
        image_markdown = ""
        if self.featured_image_url.get():
            image_url = self.featured_image_url.get()
            image_markdown = f"![Featured Image]({image_url})\n\n"
        elif self.featured_image_path:
            image_url = f"file://{self.featured_image_path}"
            image_markdown = f"![Featured Image]({image_url})\n\n"

        markdown_text = image_markdown + markdown_text

        html = markdown.markdown(markdown_text)
        self.preview_html.set_html(html)

    def get_user_id(self):
        token = self.api_token.get()
        if not token:
            messagebox.showwarning("Token Required", "Please enter your Medium API token.")
            return

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        response = requests.get("https://api.medium.com/v1/me", headers=headers)
        if response.status_code == 200:
            data = response.json()
            self.user_id = data["data"]["id"]
            messagebox.showinfo("Success", "API token is valid.")
        else:
            messagebox.showerror(
                "Error", "Failed to get user ID. Check your API token."
            )
            self.user_id = None

    def post_to_medium(self):
        if not self.user_id:
            messagebox.showwarning("User ID Missing", "Please set your API token.")
            return

        token = self.api_token.get()
        if not token:
            messagebox.showwarning("Token Required", "Please enter your Medium API token.")
            return

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        # Prepare content
        title = self.title.get()
        markdown_text = self.content_text.get("1.0", tk.END).strip()
        tags = [tag.strip() for tag in self.tags.get().split(",") if tag.strip()]
        canonical_url = self.canonical_url.get()
        publish_status = self.publish_status.get()
        notify_followers = self.notify_followers.get()
        license = self.license.get()

        if not title or not markdown_text:
            messagebox.showwarning("Missing Information", "Title and content are required.")
            return

        # If featured image is set, upload it and insert into content
        if self.featured_image_path:
            image_url = self.upload_image_to_imgur(self.featured_image_path)
            if image_url:
                # Insert image at the top of the content
                image_markdown = f"![Featured Image]({image_url})\n\n"
                markdown_text = image_markdown + markdown_text
            else:
                messagebox.showerror("Error", "Failed to upload featured image.")
                return
        elif self.featured_image_url.get():
            image_url = self.featured_image_url.get()
            image_markdown = f"![Featured Image]({image_url})\n\n"
            markdown_text = image_markdown + markdown_text

        # Prepare data
        data = {
            "title": title,
            "contentFormat": "markdown",
            "content": markdown_text,
            "tags": tags if tags else [],
            "canonicalUrl": canonical_url if canonical_url else "",
            "publishStatus": publish_status,
            "license": license,
            "notifyFollowers": notify_followers,
        }

        post_headers = headers.copy()
        post_headers["Content-Type"] = "application/json"

        url = f"https://api.medium.com/v1/users/{self.user_id}/posts"

        response = requests.post(url, headers=post_headers, json=data)
        if response.status_code == 201:
            post_data = response.json()
            post_url = post_data["data"]["url"]
            messagebox.showinfo("Success", f"Post published successfully: {post_url}")
        else:
            messagebox.showerror(
                "Error",
                f"Failed to publish post. Status code: {response.status_code}\n{response.text}",
            )

    def upload_image_to_imgur(self, image_path):
        # Imgur authenticated upload API
        url = "https://api.imgur.com/3/image"
        headers = {
            "Authorization": "Client-ID YOUR_IMGUR_CLIENT_ID",  # Replace with your Imgur Client ID
        }
        with open(image_path, "rb") as image_file:
            files = {'image': image_file}
            response = requests.post(url, headers=headers, files=files)
        if response.status_code == 200:
            data = response.json()
            image_url = data["data"]["link"]
            return image_url
        else:
            return None

    def new_file(self, event=None):
        if self.content_text.edit_modified():
            if not messagebox.askyesno("Unsaved Changes", "You have unsaved changes. Do you want to discard them?"):
                return
        self.title.set("")
        self.tags.set("")
        self.canonical_url.set("")
        self.publish_status.set("draft")
        self.notify_followers.set(False)
        self.license.set("all-rights-reserved")
        self.featured_image_path = None
        self.featured_image_url.set("")
        self.image_label.config(text="No image selected")
        self.content_text.delete("1.0", tk.END)
        self.preview_html.set_html("<p>Preview will appear here</p>")
        self.current_file = None
        self.content_text.edit_modified(0)

    def open_file(self, event=None):
        if self.content_text.edit_modified():
            if not messagebox.askyesno("Unsaved Changes", "You have unsaved changes. Do you want to discard them?"):
                return
        filetypes = [("Markdown files", "*.md *.markdown"), ("All files", "*.*")]
        filename = filedialog.askopenfilename(title="Open File", filetypes=filetypes)
        if filename:
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    content = f.read()
                self.content_text.delete("1.0", tk.END)
                self.content_text.insert(tk.END, content)
                self.current_file = filename
                self.preview_content()
                self.content_text.edit_modified(0)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to open file: {str(e)}")

    def save_file(self, event=None):
        if self.current_file:
            try:
                content = self.content_text.get("1.0", tk.END)
                with open(self.current_file, "w", encoding="utf-8") as f:
                    f.write(content)
                self.content_text.edit_modified(0)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save file: {str(e)}")
        else:
            self.save_file_as()

    def save_file_as(self):
        filetypes = [("Markdown files", "*.md *.markdown"), ("All files", "*.*")]
        filename = filedialog.asksaveasfilename(
            title="Save File As", defaultextension=".md", filetypes=filetypes
        )
        if filename:
            try:
                content = self.content_text.get("1.0", tk.END)
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(content)
                self.current_file = filename
                self.content_text.edit_modified(0)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save file: {str(e)}")

    def on_exit(self):
        if self.content_text.edit_modified():
            if not messagebox.askyesno("Quit", "You have unsaved changes. Do you really wish to quit?"):
                return
        self.root.destroy()

    def generate_title(self):
        api_key = self.openai_api_key.get()
        if not api_key:
            messagebox.showwarning("API Key Required", "Please enter your OpenAI API key.")
            return

        openai.api_key = api_key

        content = self.content_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("Content Required", "Please enter some content to generate a title.")
            return

        prompt = (
            "Generate an engaging and concise title for the following article:\n\n"
            f"{content}\n\nTitle:"
        )

        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "user", "content": prompt}
                ],
                max_tokens=20,
                n=1,
                stop=None,
                temperature=0.7,
            )
            generated_title = response.choices[0].message.content.strip()
            self.title.set(generated_title)
        except openai.error.OpenAIError as e:
            messagebox.showerror("Error", f"Failed to generate title: {str(e)}")
        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred: {str(e)}")

    def suggest_tags(self):
        api_key = self.openai_api_key.get()
        if not api_key:
            messagebox.showwarning("API Key Required", "Please enter your OpenAI API key.")
            return

        openai.api_key = api_key

        content = self.content_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("Content Required", "Please enter some content to suggest tags.")
            return

        prompt = (
            "Based on the following article, suggest up to 5 relevant tags separated by commas:\n\n"
            f"{content}\n\nTags:"
        )

        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "user", "content": prompt}
                ],
                max_tokens=50,
                n=1,
                stop=None,
                temperature=0.5,
            )
            suggested_tags = response.choices[0].message.content.strip()
            self.tags.set(suggested_tags)
        except openai.error.OpenAIError as e:
            messagebox.showerror("Error", f"Failed to suggest tags: {str(e)}")
        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred: {str(e)}")

    def debounce_grammar_check(self):
        if self.grammar_check_scheduled:
            return
        self.grammar_check_scheduled = True
        self.root.after(500, self.start_grammar_check_thread)

    def start_grammar_check_thread(self):
        if self.grammar_check_thread and self.grammar_check_thread.is_alive():
            self.grammar_check_scheduled = False
            return
        content = self.content_text.get("1.0", tk.END)
        content_version = self.current_content_version
        self.grammar_check_thread = threading.Thread(target=self.check_grammar_thread, args=(content, content_version))
        self.grammar_check_thread.start()
        self.grammar_check_scheduled = False  # Reset the flag here

    def check_grammar_thread(self, content, content_version):
        matches = self.tool.check(content)
        self.grammar_check_queue.put((matches, content_version))
        self.root.after(0, self.highlight_errors_from_thread)

    def highlight_errors_from_thread(self):
        try:
            matches, content_version = self.grammar_check_queue.get_nowait()
            if content_version == self.current_content_version:
                self.highlight_errors(matches)
        except queue.Empty:
            pass

    def highlight_errors(self, matches):
        # Remove previous error highlights
        self.content_text.tag_remove("grammar_error", "1.0", tk.END)
        self.grammar_matches = matches  # Store matches

        for match in matches:
            start_index = self.content_text.index(f"1.0+{match.offset}c")
            end_index = self.content_text.index(f"{start_index}+{match.errorLength}c")
            self.content_text.tag_add("grammar_error", start_index, end_index)

        self.content_text.tag_config("grammar_error", underline=True, foreground="red")

    def show_suggestions(self, event):
        try:
            index = self.content_text.index(f"@{event.x},{event.y}")
            word_start = self.content_text.index(f"{index} wordstart")
            word_end = self.content_text.index(f"{index} wordend")
            word = self.content_text.get(word_start, word_end)

            # Check if the word is underlined (has an error)
            tags = self.content_text.tag_names(word_start)
            if "grammar_error" in tags:
                # Get suggestions from stored matches
                content = self.content_text.get("1.0", tk.END)
                offset = self.content_text.count("1.0", word_start, "chars")[0]
                error_length = len(word)
                for match in self.grammar_matches:
                    if match.offset <= offset < match.offset + match.errorLength:
                        suggestions = match.replacements
                        break
                else:
                    suggestions = []

                if suggestions:
                    menu = tk.Menu(self.root, tearoff=0)
                    for s in suggestions[:5]:
                        menu.add_command(label=s, command=lambda replacement=s: self.replace_word(word_start, word_end, replacement))
                    menu.post(event.x_root, event.y_root)
        except Exception as e:
            pass  # Handle exceptions silently

    def replace_word(self, start, end, replacement):
        self.content_text.delete(start, end)
        self.content_text.insert(start, replacement)
        self.debounce_grammar_check()

    def highlight_syntax(self):
        # Remove previous syntax highlights
        self.content_text.tag_remove("header", "1.0", tk.END)
        self.content_text.tag_remove("bold", "1.0", tk.END)
        self.content_text.tag_remove("italic", "1.0", tk.END)
        self.content_text.tag_remove("code", "1.0", tk.END)
        self.content_text.tag_remove("link", "1.0", tk.END)

        # Highlight headers
        header_patterns = [r'^(#{1,6})\s.*$']
        for pattern in header_patterns:
            self.highlight_pattern(pattern, "header", regexp=True, start="1.0", end="end", multiline=True)

        # Highlight bold text
        self.highlight_pattern(r'(?<!\*)\*\*(.+?)\*\*(?!\*)', "bold", regexp=True)

        # Highlight italic text
        self.highlight_pattern(r'(?<!\*)\*(.+?)\*(?!\*)', "italic", regexp=True)

        # Highlight code blocks
        self.highlight_pattern(r'`([^`]+)`', "code", regexp=True)

        # Highlight links
        self.highlight_pattern(r'\[([^\]]+)\]\([^)]+\)', "link", regexp=True)

        # Configure tags
        self.content_text.tag_config("header", foreground="blue")
        self.content_text.tag_config("bold", font=("TkDefaultFont", 10, "bold"))
        self.content_text.tag_config("italic", font=("TkDefaultFont", 10, "italic"))
        self.content_text.tag_config("code", foreground="green")
        self.content_text.tag_config("link", foreground="purple", underline=True)

    def highlight_pattern(self, pattern, tag, start="1.0", end="end", regexp=False, multiline=False):
        start_pos = self.content_text.index(start)
        end_pos = self.content_text.index(end)
        content = self.content_text.get(start_pos, end_pos)
        if regexp:
            flags = re.MULTILINE if multiline else 0
            matches = re.finditer(pattern, content, flags)
            for match in matches:
                match_start = f"{start}+{match.start()}c"
                match_end = f"{start}+{match.end()}c"
                self.content_text.tag_add(tag, match_start, match_end)
        else:
            idx = start_pos
            while True:
                idx = self.content_text.search(pattern, idx, stopindex=end, regexp=False)
                if not idx:
                    break
                match_end = f"{idx}+{len(pattern)}c"
                self.content_text.tag_add(tag, idx, match_end)
                idx = match_end

    def schedule_auto_save(self):
        if self.auto_save_id:
            self.root.after_cancel(self.auto_save_id)
        self.auto_save_id = self.root.after(self.auto_save_interval, self.auto_save)

    def auto_save(self):
        content = self.content_text.get("1.0", tk.END)
        try:
            with open(self.auto_save_file, "w", encoding="utf-8") as f:
                f.write(content)
            self.auto_save_message = "Auto-saved at " + time.strftime("%H:%M:%S")
            self.update_status_bar()
        except Exception as e:
            self.status_message = f"Auto-save failed: {str(e)}"
            self.update_status_bar()
        self.schedule_auto_save()

    def check_autosave(self):
        if os.path.exists(self.auto_save_file):
            if messagebox.askyesno("Recovery", "Unsaved content was found. Do you want to recover it?"):
                try:
                    with open(self.auto_save_file, "r", encoding="utf-8") as f:
                        content = f.read()
                    self.content_text.delete("1.0", tk.END)
                    self.content_text.insert(tk.END, content)
                    self.preview_content()
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to recover auto-saved content: {str(e)}")
            os.remove(self.auto_save_file)
        else:
            pass

    def set_auto_save_interval(self):
        try:
            interval = int(self.auto_save_entry.get())
            if interval <= 0:
                raise ValueError("Interval must be positive")
            self.auto_save_interval = interval * 1000
            self.status_message = f"Auto-save interval set to {interval} seconds"
            self.update_status_bar()
            self.schedule_auto_save()
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter a valid positive number for the auto-save interval.")

    def update_status_bar(self):
        content = self.content_text.get("1.0", tk.END)
        word_count = len(content.split())
        reading_time = max(1, word_count // 200) if word_count > 0 else 0
        status = f"Words: {word_count} | Estimated Reading Time: {reading_time} min"
        if self.status_message:
            status += f" | {self.status_message}"
        if self.auto_save_message:
            status += f" | {self.auto_save_message}"
        self.status_var.set(status)
        self.root.after(1000, self.update_status_bar)  # Update every second


if __name__ == "__main__":
    root = tk.Tk()
    app = MediumPosterApp(root)
    root.mainloop()
