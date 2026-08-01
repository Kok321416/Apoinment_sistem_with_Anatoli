from pathlib import Path
from PIL import Image

assets = Path(r"C:\Users\Artem\.cursor\projects\c-Users-Artem-PycharmProjects-Apoinment-sistem-with-Anatoli\assets")
out = Path(r"c:\Users\Artem\PycharmProjects\Apoinment_sistem_with_Anatoli\app\static\img\icons\ui")
out.mkdir(parents=True, exist_ok=True)

mapping = {
    "1-096311c0": "telegram",
    "2-4aabea95": "logout",
    "3-e3607126": "book",
    "4-fdb971f9": "clients",
    "5-2c582872": "profile",
    "6-225512ce": "overview",
    "7-885c96e7": "bookings",
    "8-2d746443": "services",
    "9-3ef52541": "calendars",
    "10-c784cecd": "my-bookings",
}

files = list(assets.glob("c__Users_Artem_AppData_Roaming_Cursor_User_workspaceStorage_000235c813c6832f7496d3aeb7a32586_images_*.png"))
for key, name in mapping.items():
    src = next((f for f in files if key in f.name), None)
    if not src:
        print("MISSING", key, name)
        continue
    im = Image.open(src).convert("RGBA")
    pixels = im.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if r > 230 and g > 230 and b > 230:
                pixels[x, y] = (0, 0, 0, 0)
            else:
                lum = (r + g + b) / 3
                alpha = max(0, min(255, int(255 - lum)))
                if a < 200:
                    alpha = min(alpha, a)
                pixels[x, y] = (17, 17, 17, alpha if alpha > 40 else 0)
    dest = out / f"{name}.png"
    im.save(dest, "PNG")
    print("wrote", dest.name, im.size)
print("done")
