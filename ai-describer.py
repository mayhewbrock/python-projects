import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import keyboard
import pyautogui
from PIL import Image, ImageTk
import io
import time
import torch
from transformers import (
    BlipProcessor, BlipForConditionalGeneration,
    VisionEncoderDecoderModel, ViTImageProcessor, AutoTokenizer
)
import queue
import sys
import os
from datetime import datetime

class EnhancedImageDescriber:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AI Vision Describer Pro")
        self.root.geometry("800x600")
        
        # Available models
        self.models = {
            "BLIP-base": "Salesforce/blip-image-captioning-base",
            "BLIP-large": "Salesforce/blip-image-captioning-large",
            "ViT-GPT2": "nlpconnect/vit-gpt2-image-captioning"
        }
        
        self.setup_gui()
        self.setup_variables()
        self.setup_hotkey()
        
    def setup_gui(self):
        """Setup the enhanced GUI"""
        # Menu bar
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Save Descriptions", command=self.save_descriptions)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_closing)
        
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Control panel
        control_frame = ttk.LabelFrame(main_frame, text="Controls", padding="10")
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Model selection
        ttk.Label(control_frame, text="Model:").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.model_var = tk.StringVar(value="BLIP-base")
        model_combo = ttk.Combobox(control_frame, textvariable=self.model_var, 
                                  values=list(self.models.keys()), state="readonly")
        model_combo.grid(row=0, column=1, sticky=tk.W, padx=5)
        model_combo.bind('<<ComboboxSelected>>', self.on_model_change)
        
        # Load model button
        self.load_btn = ttk.Button(control_frame, text="Load Model", 
                                  command=self.load_selected_model)
        self.load_btn.grid(row=0, column=2, padx=5)
        
        # Listening toggle
        self.listen_btn = ttk.Button(control_frame, text="Start Listening", 
                                    command=self.toggle_listening)
        self.listen_btn.grid(row=0, column=3, padx=5)
        
        # Hotkey display
        ttk.Label(control_frame, text="Hotkey:").grid(row=0, column=4, sticky=tk.W, padx=5)
        ttk.Label(control_frame, text="Ctrl+Shift+D", foreground="blue").grid(row=0, column=5, sticky=tk.W)
        
        # Status frame
        status_frame = ttk.LabelFrame(main_frame, text="Status", padding="5")
        status_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.status_label = ttk.Label(status_frame, text="Ready", foreground="green")
        self.status_label.pack(side=tk.LEFT)
        
        self.model_status = ttk.Label(status_frame, text="[Model: Not Loaded]", foreground="red")
        self.model_status.pack(side=tk.RIGHT)
        
        # Preview frame
        preview_frame = ttk.LabelFrame(main_frame, text="Last Capture Preview", padding="5")
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.preview_label = ttk.Label(preview_frame, text="No image captured yet")
        self.preview_label.pack(pady=10)
        
        # Description frame
        desc_frame = ttk.LabelFrame(main_frame, text="Descriptions", padding="5")
        desc_frame.pack(fill=tk.BOTH, expand=True)
        
        # Text area with scrollbar
        text_frame = ttk.Frame(desc_frame)
        text_frame.pack(fill=tk.BOTH, expand=True)
        
        self.text_area = scrolledtext.ScrolledText(text_frame, wrap=tk.WORD, 
                                                  height=10, font=("Consolas", 10))
        self.text_area.pack(fill=tk.BOTH, expand=True)
        
        # Bottom buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(button_frame, text="Clear", command=self.clear_text).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Copy Last", command=self.copy_last).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Save", command=self.save_descriptions).pack(side=tk.LEFT, padx=5)
        
    def setup_variables(self):
        """Initialize variables"""
        self.is_listening = False
        self.model = None
        self.processor = None
        self.tokenizer = None
        self.current_model = None
        self.last_description = ""
        self.last_image = None
        self.message_queue = queue.Queue()
        self.processing_queue = queue.Queue()
        
        # Start queue checker
        self.check_queues()
        
    def setup_hotkey(self):
        """Setup hotkey"""
        try:
            keyboard.add_hotkey('ctrl+shift+d', self.capture_and_describe)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to register hotkey: {e}")
    
    def on_model_change(self, event=None):
        """Handle model selection change"""
        self.load_btn.config(state="normal")
        self.model_status.config(text="[Model: Not Loaded]", foreground="red")
    
    def load_selected_model(self):
        """Load selected model"""
        model_name = self.model_var.get()
        model_path = self.models[model_name]
        
        def load():
            try:
                self.update_status(f"Loading {model_name}...", "blue")
                self.load_btn.config(state="disabled")
                
                if "BLIP" in model_name:
                    self.processor = BlipProcessor.from_pretrained(model_path)
                    self.model = BlipForConditionalGeneration.from_pretrained(model_path)
                else:  # ViT-GPT2
                    self.processor = ViTImageProcessor.from_pretrained(model_path)
                    self.model = VisionEncoderDecoderModel.from_pretrained(model_path)
                    self.tokenizer = AutoTokenizer.from_pretrained(model_path)
                
                # Move to GPU if available
                if torch.cuda.is_available():
                    self.model = self.model.to('cuda')
                    device = "GPU"
                else:
                    device = "CPU"
                
                self.current_model = model_name
                self.update_status(f"{model_name} loaded on {device}", "green")
                self.model_status.config(text=f"[Model: {model_name}]", foreground="green")
                self.load_btn.config(state="normal")
                
            except Exception as e:
                self.update_status(f"Error loading model: {e}", "red")
                self.load_btn.config(state="normal")
        
        threading.Thread(target=load, daemon=True).start()
    
    def toggle_listening(self):
        """Toggle listening state"""
        if self.model is None:
            messagebox.showwarning("Warning", "Please load a model first")
            return
        
        self.is_listening = not self.is_listening
        if self.is_listening:
            self.listen_btn.config(text="Stop Listening")
            self.update_status("Listening for hotkey...", "green")
        else:
            self.listen_btn.config(text="Start Listening")
            self.update_status("Stopped listening", "orange")
    
    def capture_and_describe(self):
        """Capture and describe screen"""
        if not self.is_listening:
            return
        
        if self.model is None:
            self.update_status("Please load a model first", "orange")
            return
        
        threading.Thread(target=self.process_capture, daemon=True).start()
    
    def process_capture(self):
        """Process the capture"""
        try:
            self.update_status("Capturing screen...", "blue")
            
            # Capture screen
            screenshot = pyautogui.screenshot()
            self.last_image = screenshot.copy()
            
            # Update preview
            self.update_preview(screenshot)
            
            self.update_status("Analyzing image...", "blue")
            
            # Process with model
            if "BLIP" in self.current_model:
                inputs = self.processor(screenshot, return_tensors="pt")
                if torch.cuda.is_available():
                    inputs = {k: v.to('cuda') for k, v in inputs.items()}
                
                with torch.no_grad():
                    out = self.model.generate(**inputs, max_length=50)
                description = self.processor.decode(out[0], skip_special_tokens=True)
                
            else:  # ViT-GPT2
                pixel_values = self.processor(images=screenshot, return_tensors="pt").pixel_values
                if torch.cuda.is_available():
                    pixel_values = pixel_values.to('cuda')
                
                with torch.no_grad():
                    output_ids = self.model.generate(pixel_values, max_length=50, num_beams=4)
                description = self.tokenizer.decode(output_ids[0], skip_special_tokens=True)
            
            # Store and display
            self.last_description = description
            timestamp = datetime.now().strftime("%H:%M:%S")
            formatted = f"[{timestamp}] {description}\n{'-'*60}\n"
            
            self.message_queue.put(("text", formatted))
            self.update_status("Ready", "green")
            
        except Exception as e:
            self.update_status(f"Error: {e}", "red")
    
    def update_preview(self, image):
        """Update preview image"""
        # Resize for preview
        image.thumbnail((200, 150))
        
        # Convert to PhotoImage
        photo = ImageTk.PhotoImage(image)
        
        # Update preview label
        self.preview_label.config(image=photo, text="")
        self.preview_label.image = photo  # Keep a reference
    
    def update_status(self, message, color="blue"):
        """Update status"""
        self.message_queue.put(("status", message, color))
    
    def check_queues(self):
        """Check message queues"""
        try:
            while True:
                msg = self.message_queue.get_nowait()
                if msg[0] == "status":
                    self.status_label.config(text=msg[1], foreground=msg[2])
                elif msg[0] == "text":
                    self.text_area.insert(tk.END, msg[1])
                    self.text_area.see(tk.END)
        except queue.Empty:
            pass
        
        self.root.after(100, self.check_queues)
    
    def clear_text(self):
        """Clear text area"""
        self.text_area.delete(1.0, tk.END)
    
    def copy_last(self):
        """Copy last description to clipboard"""
        if self.last_description:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.last_description)
            self.update_status("Copied to clipboard", "green")
    
    def save_descriptions(self):
        """Save descriptions to file"""
        text = self.text_area.get(1.0, tk.END).strip()
        if text:
            filename = f"descriptions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(filename, 'w') as f:
                f.write(text)
            self.update_status(f"Saved to {filename}", "green")
    
    def on_closing(self):
        """Handle closing"""
        try:
            keyboard.unhook_all()
        except:
            pass
        self.root.destroy()
        sys.exit(0)
    
    def run(self):
        """Run application"""
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.mainloop()

def main():
    print("="*50)
    print("AI Vision Describer Pro")
    print("="*50)
    print("\nRequirements:")
    print("pip install pillow pyautogui keyboard transformers torch torchvision")
    print("\nInstructions:")
    print("1. Select a model from the dropdown")
    print("2. Click 'Load Model' (first time will download the model)")
    print("3. Click 'Start Listening'")
    print("4. Press Ctrl+Shift+D to describe any screen")
    print("="*50)
    
    app = EnhancedImageDescriber()
    app.run()

if __name__ == "__main__":
    main()
