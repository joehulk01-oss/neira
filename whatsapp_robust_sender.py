import time
import subprocess
import sys
try:
    import win32gui
    import win32con
    import pyautogui
except ImportError:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'pywin32', 'pyautogui'])
    import win32gui
    import win32con
    import pyautogui

def bring_window_to_front(window_title_keyword="WhatsApp"):
    target_hwnd = None
    def enum_windows_callback(hwnd, extra):
        nonlocal target_hwnd
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if window_title_keyword.lower() in title.lower():
                target_hwnd = hwnd
                return False
        return True
    
    try:
        win32gui.EnumWindows(enum_windows_callback, None)
    except Exception:
        pass
    
    if not target_hwnd:
        return False, "WhatsApp window tidak ditemukan di daftar jendela aktif."
    
    # Restore jika minimized
    win32gui.ShowWindow(target_hwnd, win32con.SW_RESTORE)
    win32gui.SetForegroundWindow(target_hwnd)
    time.sleep(0.5)
    
    # Verifikasi foreground
    current_hwnd = win32gui.GetForegroundWindow()
    if current_hwnd != target_hwnd:
        # Coba paksa attach thread input jika terhalang Windows focus policy
        return False, "Gagal mengunci fokus jendela WhatsApp (terhalang foreground lock)."
    
    return True, target_hwnd

def send_whatsapp_message(contact_name, message):
    print(f"[*] Mencoba mengaktifkan WhatsApp untuk kontak: {contact_name}")
    ok, hwnd_or_err = bring_window_to_front("WhatsApp")
    
    if not ok:
        # Coba luncurkan WhatsApp jika belum berjalan
        print("[!] WhatsApp belum di foreground. Membuka aplikasi...")
        subprocess.run(["powershell", "-Command", "Start-Process shell:AppsFolder\\5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App"], shell=True)
        time.sleep(2.5)
        ok, hwnd_or_err = bring_window_to_front("WhatsApp")
        if not ok:
            return False, f"Verifikasi Gagal: Tidak bisa memfokuskan WhatsApp ({hwnd_or_err}). Membatalkan pengetikan agar tidak bocor ke OS search!"

    # Bersihkan search bar Windows jika tadi sempat terbuka
    pyautogui.press('esc')
    time.sleep(0.2)
    pyautogui.press('esc')
    time.sleep(0.3)

    # Langkah aman: Fokus ke kolom pencarian WhatsApp (Ctrl + F)
    print("[*] Mengarahkan fokus ke pencarian kontak WhatsApp (Ctrl+F)...")
    pyautogui.hotkey('ctrl', 'f')
    time.sleep(0.5)
    
    # Bersihkan kolom chat search
    pyautogui.hotkey('ctrl', 'a')
    pyautogui.press('backspace')
    time.sleep(0.2)
    
    # Ketik nama kontak dengan interval aman
    print(f"[*] Mengetik nama kontak: {contact_name}")
    pyautogui.write(contact_name, interval=0.08)
    time.sleep(1.2)
    
    # Pilih kontak teratas hasil pencarian
    pyautogui.press('down')
    time.sleep(0.3)
    pyautogui.press('enter')
    time.sleep(1.0)
    
    # Ketik dan kirim pesan
    print(f"[*] Mengetik pesan: {message}")
    pyautogui.write(message, interval=0.04)
    time.sleep(0.5)
    pyautogui.press('enter')
    time.sleep(0.5)
    
    return True, f"Pesan berhasil dikirim ke {contact_name} dengan verifikasi fokus jendela aktif."

if __name__ == "__main__":
    target = "Tips"
    msg = "Jangan lupa ingat Neira"
    status, result = send_whatsapp_message(target, msg)
    print(f"STATUS: {status} | RESULT: {result}")
    if not status:
        sys.exit(1)
