"""
Automated Test for Neira Smart Browser (OpenMuse architecture).
Verifies:
1. Navigation to HTML form page
2. Interactive tree snapshot & element numbered IDs (#1, #2, etc.)
3. Filling text inputs by element_id
4. Clicking buttons by element_id
5. Screenshot trace capture
"""

import os
import sys
import tempfile
from pathlib import Path

# Add Mark-LIV-main to path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from core.smart_browser_engine import get_browser
from skills.admin.smart_browser import smart_browser

def test_smart_browser_e2e():
    print("==================================================")
    print("  TEST E2E: Neira Smart Browser (OpenMuse Flow)")
    print("==================================================")

    # 1. Create a dummy local HTML form to test realistic form filling & button clicks
    html_content = """<!DOCTYPE html>
    <html>
    <head><title>Form Pendaftaran Neira Test</title></head>
    <body style="font-family: sans-serif; padding: 20px;">
        <h2>Formulir Pengujian Otomasi Browser Neira</h2>
        <form id="test-form">
            <div>
                <label>Nama Lengkap:</label><br>
                <input type="text" id="nama" name="nama" placeholder="Masukkan nama Anda">
            </div><br>
            <div>
                <label>Email:</label><br>
                <input type="email" id="email" name="email" placeholder="contoh@domain.com">
            </div><br>
            <div>
                <label>Pilihan Paket:</label><br>
                <select id="paket" name="paket">
                    <option value="basic">Paket Basic</option>
                    <option value="pro">Paket Pro</option>
                    <option value="enterprise">Paket Enterprise</option>
                </select>
            </div><br>
            <button type="button" id="btn-submit" onclick="submitForm()">Kirim Data</button>
        </form>
        <div id="result" style="margin-top: 20px; font-weight: bold; color: green;"></div>
        <script>
            function submitForm() {
                const n = document.getElementById('nama').value;
                const e = document.getElementById('email').value;
                const p = document.getElementById('paket').value;
                document.getElementById('result').innerText = 'STATUS_SUKSES: ' + n + ' (' + e + ') - ' + p;
            }
        </script>
    </body>
    </html>
    """

    temp_html = Path(tempfile.gettempdir()) / "neira_browser_test.html"
    temp_html.write_text(html_content, encoding="utf-8")
    local_url = temp_html.as_uri()

    print(f"\n[1] Membuka URL lokal: {local_url}")
    nav_res = smart_browser({"action": "navigate", "url": local_url})
    print(nav_res)
    assert "Formulir Pengujian Otomasi Browser Neira" in nav_res or "Form Pendaftaran" in nav_res

    # 2. Ambil snapshot elemen
    browser = get_browser()
    snap = browser.snapshot()
    raw_elements = snap.get("raw_elements", [])
    print(f"\n[2] Jumlah elemen interaktif terdeteksi: {len(raw_elements)}")
    
    nama_id = None
    email_id = None
    submit_id = None

    for el in raw_elements:
        label = (el.get("label") or "").lower()
        if "masukkan nama" in label or el.get("type") == "text":
            nama_id = el["id"]
        elif "contoh@domain" in label or el.get("type") == "email":
            email_id = el["id"]
        elif "kirim data" in label or el.get("role") == "button":
            submit_id = el["id"]

    print(f"    -> Input Nama ID: #{nama_id}")
    print(f"    -> Input Email ID: #{email_id}")
    print(f"    -> Button Submit ID: #{submit_id}")
    
    assert nama_id is not None, "Field nama harus terdeteksi dengan numeric ID"
    assert email_id is not None, "Field email harus terdeteksi dengan numeric ID"
    assert submit_id is not None, "Button submit harus terdeteksi dengan numeric ID"

    # 3. Test Type Text via Skill
    print(f"\n[3] Mengisi kolom Nama (ID #{nama_id}) dan Email (ID #{email_id})...")
    type_res1 = smart_browser({"action": "type", "element_id": nama_id, "text": "Jarvis Neira"})
    print("    Type Nama result:", type_res1.split("\n")[0])
    
    type_res2 = smart_browser({"action": "type", "element_id": email_id, "text": "neira@ai.local"})
    print("    Type Email result:", type_res2.split("\n")[0])

    # 4. Test Click Button Submit
    print(f"\n[4] Mengklik tombol Submit (ID #{submit_id})...")
    click_res = smart_browser({"action": "click", "element_id": submit_id})
    print("    Click result:", click_res.split("\n")[0])

    # 5. Verifikasi isi form terkirim
    final_snap = browser.snapshot()
    print("\n[5] Verifikasi hasil di halaman:")
    page_text = browser._run_coroutine(browser._page.evaluate("document.body.innerText"))
    print(page_text.strip())
    assert "STATUS_SUKSES: Jarvis Neira (neira@ai.local)" in page_text

    # 6. Test Screenshot
    print("\n[6] Mengambil screenshot trace...")
    shot_res = smart_browser({"action": "screenshot", "filename": "test_e2e_success.png"})
    print("   ", shot_res)

    print("\n[SUCCESS] SEMUA PENGUJIAN SKILL SMART BROWSER BERHASIL 100%!")

if __name__ == "__main__":
    test_smart_browser_e2e()
