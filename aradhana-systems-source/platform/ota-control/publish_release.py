"""Create a signed AIS OTA release from one verified ZIP bundle."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography import x509
from cryptography.x509.oid import NameOID

DEFAULT_ROOT = Path(r"C:\AradhanaSystems\ota-releases")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def initialize_keys(root: Path) -> None:
    keys = root / "keys"
    private_path, public_path, certificate_path = keys / "ota-private.pem", keys / "ota-public.pem", keys / "ota-public.cer"
    keys.mkdir(parents=True, exist_ok=True)
    if private_path.exists() or public_path.exists() or certificate_path.exists():
        if private_path.exists() and public_path.exists() and certificate_path.exists():
            return
        raise RuntimeError("OTA signing material is incomplete; restore all files before publishing.")
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    private_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                               serialization.NoEncryption()))
    public_path.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,
                                                          serialization.PublicFormat.SubjectPublicKeyInfo))
    now = datetime.now(UTC)
    certificate = (x509.CertificateBuilder()
                   .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "AIS OTA Release Signing")]))
                   .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "AIS OTA Release Signing")]))
                   .public_key(key.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(now).not_valid_after(now + timedelta(days=3652))
                   .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                   .sign(key, hashes.SHA256()))
    certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.DER))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", choices=("beta", "stable"))
    parser.add_argument("--target")
    parser.add_argument("--version")
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--notes", default="")
    parser.add_argument("--root", default=DEFAULT_ROOT, type=Path)
    parser.add_argument("--initialize-keys", action="store_true")
    args = parser.parse_args()
    if args.initialize_keys:
        initialize_keys(args.root)
        print(json.dumps({"initialized": str(args.root / "keys" / "ota-public.cer")}))
        return
    if not args.channel or not args.target or not args.version or not args.bundle:
        raise SystemExit("channel, target, version, and bundle are required when publishing")
    if not args.target.replace("-", "").replace("_", "").isalnum():
        raise SystemExit("target may contain only letters, numbers, hyphens, and underscores")
    if Path(args.version).name != args.version:
        raise SystemExit("version may not contain a path")
    if not args.bundle.is_file() or args.bundle.suffix.lower() != ".zip":
        raise SystemExit("bundle must be an existing .zip file")
    private_path = args.root / "keys" / "ota-private.pem"
    if not private_path.is_file():
        raise SystemExit("OTA signing key missing; run once with --initialize-keys")

    filename = f"{args.target}-{args.version}.zip"
    destination = args.root / "channels" / args.channel / args.target / "artifacts" / args.version / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.bundle, destination)
    payload = {
        "schema": 1,
        "channel": args.channel,
        "target": args.target,
        "version": args.version,
        "created_at": datetime.now(UTC).isoformat(),
        "notes": args.notes[:1000],
        "artifact": {"filename": filename, "sha256": sha256(destination)},
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    key = serialization.load_pem_private_key(private_path.read_bytes(), password=None)
    signature = key.sign(payload_bytes, padding.PKCS1v15(), hashes.SHA256())
    envelope = {"payload_b64": base64.b64encode(payload_bytes).decode("ascii"),
                "signature_b64": base64.b64encode(signature).decode("ascii")}
    current = args.root / "channels" / args.channel / args.target / "current.json"
    current.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
    print(json.dumps({"published": str(current), "version": args.version, "sha256": payload["artifact"]["sha256"]}))


if __name__ == "__main__":
    main()
