"""gen_certs.py — generate TLS cert untuk gateway Neira. DINAMIS, tanpa IP hardcode.

Struktur:
  ca.pem / ca-key.pem   → CA lokal, dibuat SEKALI (kalau belum ada). CA ini yang
                          di-embed di APK (res/raw/neira_cert) sebagai trust anchor,
                          jadi leaf boleh berubah-ubah tanpa harus rebuild APK.
  cert.pem / key.pem    → leaf server, DIBUAT ULANG SETIAP start dengan
                          SAN = semua IP LAN aktif + localhost. Tahan ganti IP
                          (WiFi tetangga / hotspot HP / tether HP).

Dipanggil otomatis oleh run_local.bat sebelum uvicorn start:
  ..\\Mark-LIV-main\\.venv\\Scripts\\python.exe certs\\gen_certs.py

Dependency: cryptography  (pip install cryptography di venv Mark-LIV-main)
"""
from __future__ import annotations

import datetime
import ipaddress
import socket
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

HERE = Path(__file__).resolve().parent
CA_KEY = HERE / "ca-key.pem"
CA_CRT = HERE / "ca.pem"
LEAF_KEY = HERE / "key.pem"
LEAF_CRT = HERE / "cert.pem"
# Trust anchor untuk APK — di-sync otomatis supaya tidak lupa update.
ANDROID_ANCHOR = (
    HERE.parent.parent
    / "neira-android" / "app" / "src" / "main" / "res" / "raw" / "neira_cert"
)

UTC = datetime.timezone.utc


def _local_ips() -> list[str]:
    """Semua IPv4 non-loopback yang aktif di mesin ini — dideteksi, bukan hardcode."""
    ips: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127."):
                ips.add(ip)
    except Exception:
        pass
    try:  # trik UDP-connect: interface default untuk keluar
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ips.add(s.getsockname()[0])
        finally:
            s.close()
    except Exception:
        pass
    ips.discard("0.0.0.0")
    return sorted(ips)


def _new_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _save_key(key: rsa.RSAPrivateKey, path: Path) -> None:
    path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ))


def ensure_ca() -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    """Muat CA yang ada, atau buat baru (sekali seumur proyek)."""
    if CA_CRT.exists() and CA_KEY.exists():
        key = serialization.load_pem_private_key(CA_KEY.read_bytes(), password=None)
        crt = x509.load_pem_x509_certificate(CA_CRT.read_bytes())
        return key, crt

    key = _new_key()
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "Neira Local CA"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Neira"),
    ])
    now = datetime.datetime.now(UTC)
    crt = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=3650))  # 10 tahun
        .add_extension(x509.BasicConstraints(ca=True, path_length=1), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=False,
                key_encipherment=False, data_encipherment=False,
                key_agreement=False, key_cert_sign=True, crl_sign=True,
                encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False
        )
        .sign(key, hashes.SHA256())
    )
    _save_key(key, CA_KEY)
    CA_CRT.write_bytes(crt.public_bytes(serialization.Encoding.PEM))
    print(f"[cert] CA lokal baru dibuat: {CA_CRT.name} (berlaku 10 tahun)")
    return key, crt


def issue_leaf(ca_key: rsa.RSAPrivateKey, ca_crt: x509.Certificate) -> list[str]:
    """Terbitkan leaf server baru dengan SAN = semua IP LAN aktif + localhost."""
    ips = _local_ips()
    san: list[x509.GeneralName] = [x509.DNSName("localhost")]
    for ip in ips:
        try:
            san.append(x509.IPAddress(ipaddress.ip_address(ip)))
        except ValueError:
            continue

    key = _new_key()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Neira Gateway")])
    now = datetime.datetime.now(UTC)
    crt = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(ca_crt.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=825))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    _save_key(key, LEAF_KEY)
    LEAF_CRT.write_bytes(crt.public_bytes(serialization.Encoding.PEM))
    return ips


def sync_android_anchor(ca_crt: x509.Certificate) -> None:
    """Tulis ulang raw/neira_cert (DER) dari CA — biar APK selalu cocok."""
    try:
        ANDROID_ANCHOR.parent.mkdir(parents=True, exist_ok=True)
        ANDROID_ANCHOR.write_bytes(ca_crt.public_bytes(serialization.Encoding.DER))
        print(f"[cert] Trust anchor APK disinkron: {ANDROID_ANCHOR}")
    except Exception as exc:  # noqa: BLE001 — sinkron gagal bukan fatal
        print(f"[cert] (peringatan) gagal sync raw cert APK: {exc}")


def main() -> int:
    ca_key, ca_crt = ensure_ca()
    ips = issue_leaf(ca_key, ca_crt)
    sync_android_anchor(ca_crt)
    print(f"[cert] Leaf server diterbitkan — SAN: localhost + {', '.join(ips) or '(tidak ada IP LAN)'}")
    print(f"[cert] Dipakai uvicorn: {LEAF_CRT.name} / {LEAF_KEY.name}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"[cert] GAGAL: {exc}", file=sys.stderr)
        sys.exit(1)
