import os

base = os.path.join(os.path.dirname(__file__), "..", "app", "static", "diagnostics", "eyes")
os.makedirs(base, exist_ok=True)
for i in range(1, 13):
    lx = 65 + (i % 4) * 3
    rx = 135 + (i % 3) * 4
    py = 48 + (i % 5) * 2
    path = os.path.join(base, f"eye-{i:02d}.svg")
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100" role="img" aria-hidden="true">'
            f'<rect width="200" height="100" fill="#e8ecf1" rx="8"/>'
            f'<ellipse cx="65" cy="50" rx="28" ry="18" fill="#fff" stroke="#94a3b8" stroke-width="2"/>'
            f'<ellipse cx="135" cy="50" rx="28" ry="18" fill="#fff" stroke="#94a3b8" stroke-width="2"/>'
            f'<circle cx="{lx}" cy="{py}" r="7" fill="#334155"/>'
            f'<circle cx="{rx}" cy="{py}" r="7" fill="#334155"/>'
            f"</svg>"
        )
print("generated", len(os.listdir(base)))
