import os
import sys
import argparse
import cv2

# Bootstrap DLLs trước khi import bất kỳ thư viện CUDA nào
from app.utils.ai.gpu_bootstrap import init_windows_cuda_path
init_windows_cuda_path("pre")

# Import torch trước paddle để tránh xung đột DLL (nếu torch load được)
try:
    import torch
except (ImportError, OSError):
    pass

from app.utils.ai.ship_id_recognizer import ShipIdRecognizer

def main():
    parser = argparse.ArgumentParser(description="Ship ID Recognition CLI")
    parser.add_argument("--image", type=str, required=True, help="Path to boat crop image")
    parser.add_argument("--gpu", action="store_true", help="Force use GPU")
    args = parser.parse_args()

    if not os.path.exists(args.image):
        print(f"Error: File not found {args.image}")
        return

    img = cv2.imread(args.image)
    if img is None:
        print(f"Error: Could not read image {args.image}")
        return

    print(f"Initializing recognizer (GPU={args.gpu or 'auto'})...")
    recognizer = ShipIdRecognizer(use_gpu=args.gpu if args.gpu else None)

    print(f"Processing {args.image}...")
    results = recognizer.recognize_bgr(img)

    print("\n" + "="*30)
    print("DETECTION RESULTS")
    print("="*30)
    
    if not results:
        print("No valid ship ID found.")
    else:
        for res in results:
            print(f"SHIP ID: {res['id']}")
            print(f"Confidence: {res['confidence']:.2f}")
            print(f"Raw text: {res['raw_text']}")
            print("-" * 20)

if __name__ == "__main__":
    main()
