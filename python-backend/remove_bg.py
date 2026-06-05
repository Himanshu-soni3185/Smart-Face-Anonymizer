import cv2
import numpy as np

def remove_white_bg(input_path, output_path):
    # Read image including alpha channel if it exists, otherwise color
    img = cv2.imread(input_path, cv2.IMREAD_UNCHANGED)
    
    # If it doesn't have an alpha channel, add one
    if img.shape[2] == 3:
        b, g, r = cv2.split(img)
        alpha = np.ones(b.shape, dtype=b.dtype) * 255
        img = cv2.merge((b, g, r, alpha))

    # Create a mask of white pixels (using a threshold)
    lower_white = np.array([230, 230, 230, 255])
    upper_white = np.array([255, 255, 255, 255])
    
    # Actually, let's just check RGB
    b, g, r, a = cv2.split(img)
    white_mask = (b > 230) & (g > 230) & (r > 230)
    
    # Set alpha to 0 for white pixels
    a[white_mask] = 0
    
    # Merge back
    img_transparent = cv2.merge((b, g, r, a))
    
    cv2.imwrite(output_path, img_transparent)
    print("Background removed successfully using OpenCV!")

if __name__ == "__main__":
    in_img = r"C:\Users\Devendra Soni\.gemini\antigravity\brain\0751501c-a591-4a51-b2c6-a881c85c0a2f\face_anonymizer_icon_nobg_1780670636101.png"
    out_img = r"c:\Users\Devendra Soni\Documents\projects_02\face-blur-app\app\icon.png"
    remove_white_bg(in_img, out_img)
