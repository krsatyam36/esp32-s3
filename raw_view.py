import cv2
import urllib.request
import numpy as np
import time
from config import ESP32_IP

print(f"Connecting to {ESP32_IP}...")

try:
    stream = urllib.request.urlopen(ESP32_IP, timeout=10)
except Exception as e:
    print(f"CRITICAL ERROR: {e}")
    print("Check if the board is on and the IP is correct.")
    exit()

print("Connected! Buffer filling...")
bytes_data = b''

# Initialize variables for FPS calculation
prev_time = 0
fps_avg = 0

while True:
    try:
        # Read 4KB of data at a time
        bytes_data += stream.read(4096)
        
        # Look for JPEG Start (0xff 0xd8) and End (0xff 0xd9) markers
        a = bytes_data.find(b'\xff\xd8')
        b = bytes_data.find(b'\xff\xd9')

        if a != -1 and b != -1:
            # Extract the raw JPEG image bytes
            jpg = bytes_data[a:b+2]
            # Remove those bytes from the buffer
            bytes_data = bytes_data[b+2:]
            
            # Decode to image matrix
            img = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
            
            if img is not None:
                # --- CALCULATE FPS ---
                curr_time = time.time()
                # Prevent division by zero
                time_diff = curr_time - prev_time if (curr_time - prev_time) > 0 else 0.001
                
                fps = 1.0 / time_diff
                prev_time = curr_time
                
                # Smooth the FPS using a simple moving average for readability
                fps_avg = (fps_avg * 0.9) + (fps * 0.1)

                # Draw the FPS counter on the image
                cv2.putText(img, f"FPS: {fps_avg:.1f}", (10, 30), 
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                
                cv2.imshow('Live ESP32 Feed', img)
            
            # Press 'q' to quit
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
                
    except Exception as e:
        print(f"Stream error: {e}")
        break

cv2.destroyAllWindows()
