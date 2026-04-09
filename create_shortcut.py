import os
from PIL import Image, ImageChops
from win32com.client import Dispatch

def trim(im):
    # Convert to RGBA
    im = im.convert('RGBA')
    # Use alpha channel if it's already useful
    alpha = im.split()[-1]
    if alpha.getextrema()[0] < 255: # If there's some transparency already
        bbox = alpha.getbbox()
    else:
        # If no transparency, try to treat white as transparency
        data = im.getdata()
        new_data = []
        for item in data:
            # If color is near-white, make it transparent
            if item[0] > 240 and item[1] > 240 and item[2] > 240:
                new_data.append((255, 255, 255, 0))
            else:
                new_data.append(item)
        im.putdata(new_data)
        bbox = im.getbbox()
        
    if bbox:
        return im.crop(bbox)
    return im

def create_shortcut_with_icon():
    png_path = r"C:\Users\ASUS\anaconda3\.gemini\antigravity\brain\ee6c25ea-8104-4b20-8e71-e2d8fd98e6f9\media__1775626275284.png"
    # Fallback to local user path if the above absolute path doesn't resolve in some contexts
    if not os.path.exists(png_path):
         png_path = os.path.join(os.environ['APPDATA'], r"..\Local\Packages\PythonSoftwareFoundation.Python.3.10_qbz5n2kfra8p0\LocalCache\local-packages\Python310\site-packages\.gemini\antigravity\brain\ee6c25ea-8104-4b20-8e71-e2d8fd98e6f9\media__1775626275284.png")
    # Actually, simpler: I'll just use the path I found in view_file.
    png_path = r"C:\Users\ASUS\.gemini\antigravity\brain\ee6c25ea-8104-4b20-8e71-e2d8fd98e6f9\media__1775626275284.png"
    project_dir = r"C:\Users\ASUS\OneDrive\Desktop\NeuroPulseAI"
    ico_path = os.path.join(project_dir, "logo_v4.ico")
    
    print(f"Loading {png_path}...")
    img = Image.open(png_path)
    
    # 1. Trim empty space
    print("Trimming empty space from logo...")
    img = trim(img)
    
    # 2. Make it square
    width, height = img.size
    new_size = max(width, height)
    new_img = Image.new("RGBA", (new_size, new_size), (0, 0, 0, 0))
    # Center the original
    new_img.paste(img, ((new_size - width) // 2, (new_size - height) // 2))
    img = new_img
    
    # 3. Resize and Save
    print("Saving ICO...")
    img = img.resize((256, 256), Image.LANCZOS)
    img.save(ico_path, format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (32, 32)])
    
    # Update Shortcut
    desktop = os.path.join(os.path.join(os.environ['USERPROFILE']), 'OneDrive', 'Desktop')
    if not os.path.exists(desktop):
        desktop = os.path.join(os.path.join(os.environ['USERPROFILE']), 'Desktop')
    
    path = os.path.join(desktop, "NeuroPulseAI Plotter.lnk")
    target = os.path.join(project_dir, "launch_plotter.bat")
    
    shell = Dispatch('WScript.Shell')
    shortcut = shell.CreateShortCut(path)
    shortcut.Targetpath = target
    shortcut.WorkingDirectory = project_dir
    shortcut.IconLocation = ico_path
    shortcut.save()
    print("Desktop shortcut updated with cropped icon.")

if __name__ == "__main__":
    try:
        create_shortcut_with_icon()
    except Exception as e:
        print(f"Error: {e}")
