from PIL import Image

def fix_icon():
    in_path = r"C:\Users\Devendra Soni\.gemini\antigravity\brain\0751501c-a591-4a51-b2c6-a881c85c0a2f\face_anonymizer_icon_nobg_1780670636101.png"
    out_path = r"c:\Users\Devendra Soni\Documents\projects_02\face-blur-app\app\icon.png"
    
    img = Image.open(in_path)
    img = img.convert("RGBA")
    datas = img.getdata()
    
    newData = []
    for item in datas:
        if item[0] > 230 and item[1] > 230 and item[2] > 230:
            newData.append((255, 255, 255, 0))
        else:
            newData.append(item)
            
    img.putdata(newData)
    img.save(out_path, format="PNG", optimize=True)
    print("Fixed icon.png using PIL!")

if __name__ == "__main__":
    fix_icon()
