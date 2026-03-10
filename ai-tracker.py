import sys
import cv2
import numpy as np
import mss
import torch
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QSlider, 
                             QCheckBox, QGroupBox)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap
from ultralytics import YOLO

class DetectionThread(QThread):
    change_pixmap_signal = pyqtSignal(np.ndarray)
    fps_signal = pyqtSignal(float)
    
    def __init__(self):
        super().__init__()
        self.running = True
        self.show_boxes = True
        self.confidence_threshold = 0.5
        self.model = YOLO('yolov8n.pt')  # Using YOLOv8 nano model for speed
        
    def run(self):
        import time
        with mss.mss() as sct:
            monitor = sct.monitors[1]  # Primary monitor
            fps_counter = 0
            fps_time = time.time()
            
            while self.running:
                # Capture screen
                screenshot = sct.grab(monitor)
                frame = np.array(screenshot)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                
                # Run detection
                results = self.model(frame, conf=self.confidence_threshold)
                
                # Draw boxes if enabled
                if self.show_boxes:
                    for r in results:
                        boxes = r.boxes
                        for box in boxes:
                            # Check if it's a person (class 0 in COCO dataset)
                            if int(box.cls[0]) == 0:
                                x1, y1, x2, y2 = map(int, box.xyxy[0])
                                conf = float(box.conf[0])
                                
                                # Draw bounding box
                                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                                
                                # Draw confidence text
                                label = f'Person: {conf:.2f}'
                                cv2.putText(frame, label, (x1, y1-10), 
                                          cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                
                # Calculate FPS
                fps_counter += 1
                if time.time() - fps_time >= 1.0:
                    fps = fps_counter / (time.time() - fps_time)
                    self.fps_signal.emit(fps)
                    fps_counter = 0
                    fps_time = time.time()
                
                # Emit frame
                self.change_pixmap_signal.emit(frame)
    
    def stop(self):
        self.running = False
        self.wait()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.initDetection()
        
    def initUI(self):
        self.setWindowTitle("People Detection - Screen Overlay")
        self.setGeometry(100, 100, 1200, 800)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QHBoxLayout(central_widget)
        
        # Left panel - Controls
        left_panel = QWidget()
        left_panel.setMaximumWidth(250)
        left_layout = QVBoxLayout(left_panel)
        
        # Detection controls group
        detection_group = QGroupBox("Detection Controls")
        detection_layout = QVBoxLayout()
        
        # Toggle boxes checkbox
        self.toggle_boxes = QCheckBox("Show Bounding Boxes")
        self.toggle_boxes.setChecked(True)
        self.toggle_boxes.stateChanged.connect(self.toggle_detection_boxes)
        detection_layout.addWidget(self.toggle_boxes)
        
        # Confidence threshold slider
        detection_layout.addWidget(QLabel("Confidence Threshold:"))
        self.confidence_slider = QSlider(Qt.Horizontal)
        self.confidence_slider.setMinimum(0)
        self.confidence_slider.setMaximum(100)
        self.confidence_slider.setValue(50)
        self.confidence_slider.setTickInterval(10)
        self.confidence_slider.setTickPosition(QSlider.TicksBelow)
        self.confidence_slider.valueChanged.connect(self.update_confidence)
        detection_layout.addWidget(self.confidence_slider)
        
        self.confidence_label = QLabel("Confidence: 0.50")
        detection_layout.addWidget(self.confidence_label)
        
        detection_group.setLayout(detection_layout)
        left_layout.addWidget(detection_group)
        
        # Stats group
        stats_group = QGroupBox("Statistics")
        stats_layout = QVBoxLayout()
        
        self.fps_label = QLabel("FPS: --")
        stats_layout.addWidget(self.fps_label)
        
        self.people_count_label = QLabel("People Detected: --")
        stats_layout.addWidget(self.people_count_label)
        
        stats_group.setLayout(stats_layout)
        left_layout.addWidget(stats_group)
        
        # Start/Stop button
        self.start_stop_btn = QPushButton("Stop Detection")
        self.start_stop_btn.clicked.connect(self.toggle_detection)
        left_layout.addWidget(self.start_stop_btn)
        
        # Info label
        info_text = """
        <b>Instructions:</b><br>
        • Green boxes show detected people<br>
        • Confidence scores shown above boxes<br>
        • Adjust threshold to filter detections<br>
        • Toggle boxes on/off as needed<br>
        <br>
        <b>Note:</b> This captures your entire screen
        """
        info_label = QLabel(info_text)
        info_label.setWordWrap(True)
        info_label.setStyleSheet("background-color: #f0f0f0; padding: 10px; border-radius: 5px;")
        left_layout.addWidget(info_label)
        
        left_layout.addStretch()
        
        # Right panel - Video display
        self.video_label = QLabel()
        self.video_label.setMinimumSize(800, 600)
        self.video_label.setStyleSheet("border: 2px solid black; background-color: black;")
        self.video_label.setAlignment(Qt.AlignCenter)
        
        # Add panels to main layout
        main_layout.addWidget(left_panel)
        main_layout.addWidget(self.video_label, 1)
        
    def initDetection(self):
        self.detection_thread = DetectionThread()
        self.detection_thread.change_pixmap_signal.connect(self.update_image)
        self.detection_thread.fps_signal.connect(self.update_fps)
        self.detection_thread.start()
        self.detection_active = True
        
    def update_image(self, frame):
        """Updates the video label with new frame"""
        # Count people in frame
        if hasattr(self, 'detection_thread') and self.detection_thread.show_boxes:
            # Simple count - in a real app you'd want to count actual detections
            cv2.putText(frame, f"Press 'Toggle Boxes' to show/hide", (10, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # Convert frame to Qt format
        rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
        
        # Scale image to fit label while maintaining aspect ratio
        scaled_pixmap = QPixmap.fromImage(qt_image).scaled(
            self.video_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        
        self.video_label.setPixmap(scaled_pixmap)
        
    def update_fps(self, fps):
        self.fps_label.setText(f"FPS: {fps:.1f}")
        
    def toggle_detection_boxes(self, state):
        if self.detection_thread:
            self.detection_thread.show_boxes = (state == Qt.Checked)
            
    def update_confidence(self, value):
        confidence = value / 100.0
        self.confidence_label.setText(f"Confidence: {confidence:.2f}")
        if self.detection_thread:
            self.detection_thread.confidence_threshold = confidence
            
    def toggle_detection(self):
        if self.detection_active:
            self.detection_thread.stop()
            self.start_stop_btn.setText("Start Detection")
            self.detection_active = False
        else:
            self.detection_thread = DetectionThread()
            self.detection_thread.change_pixmap_signal.connect(self.update_image)
            self.detection_thread.fps_signal.connect(self.update_fps)
            self.detection_thread.show_boxes = self.toggle_boxes.isChecked()
            self.detection_thread.confidence_threshold = self.confidence_slider.value() / 100.0
            self.detection_thread.start()
            self.start_stop_btn.setText("Stop Detection")
            self.detection_active = True
            
    def closeEvent(self, event):
        if hasattr(self, 'detection_thread'):
            self.detection_thread.stop()
        event.accept()

def main():
    app = QApplication(sys.argv)
    
    # Check if CUDA is available
    if torch.cuda.is_available():
        print(f"CUDA available! Using GPU: {torch.cuda.get_device_name(0)}")
    else:
        print("CUDA not available. Using CPU (may be slower)")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
