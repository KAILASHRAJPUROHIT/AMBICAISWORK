#!/usr/bin/env sh
# Emits manifest.json — the signed fleet-update contract.
# Args: VERSION CHANNEL SERVER_IMG WEB_IMG APK_FILE APK_VERSIONCODE APK_CHECKSUM PROTO_VERSION AOSP_APK_FILE
set -eu
python3 - "$@" <<'PY'
import sys, json, hashlib
ver, ch, server_img, web_img, apk, apk_vc, apk_ck, proto, aosp_apk = sys.argv[1:10]
sha = hashlib.sha256(open(apk, "rb").read()).hexdigest()
aosp_sha = hashlib.sha256(open(aosp_apk, "rb").read()).hexdigest()
m = {
  "version": ver, "channel": ch,
  "components": {
    "serverImage": server_img, "webImage": web_img,
    "apk": {"file": apk.split("/")[-1], "versionCode": int(apk_vc),
            "sha256": sha, "signatureChecksum": apk_ck},
    "apkCn": {"file": aosp_apk.split("/")[-1], "versionCode": int(apk_vc),
              "sha256": aosp_sha, "signatureChecksum": apk_ck},
  },
  "compat": {"minAgentProtocol": "1.0", "maxAgentProtocol": proto},
}
open("manifest.json", "w").write(json.dumps(m, indent=2) + "\n")
print("wrote manifest.json")
PY
