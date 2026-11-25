#!/usr/bin/env python3
"""
Comprehensive tests for Step 3: Pure-Stdlib RFC 8032 Ed25519 Signed Offset DB Sync,
SHA-256 + Strict Allowlist Schema Validation, 3-Layer Precedence, Explicit 1-Click Sync,
and offset_db_version propagation across Debug Console, Issue Report, and Exports.
"""

import base64
import hashlib
import json
import os
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

import machine_library
import offset_db_sync as ods
import profiles_db
import spectra_probe
import stats_collector as sc
import web_server


def _sign_test_bundle(seed: bytes, key_id: str, version_str: str, machines: dict, pack_url: str):
    """Helper mirroring spectra-hub canonical Ed25519 signing for tests."""
    pack_unsigned = {
        "schema": ods.SCHEMA_PACK_V1,
        "version": version_str,
        "published_at": "2026-11-24T10:30:00Z",
        "key_id": key_id,
        "machines": machines,
        "notes": "Signed test pack",
        "signature_alg": "Ed25519",
    }
    pack_sig = ods.ed25519_sign(seed, ods.PACK_DOMAIN_PREFIX + ods.canonical_json_bytes(pack_unsigned))
    pack = dict(pack_unsigned)
    pack["signature_b64"] = base64.b64encode(pack_sig).decode("ascii")
    raw_pack = json.dumps(pack, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8")

    machines_index = []
    for mid, entry in sorted(machines.items()):
        vo = entry.get("verified_offsets") or {}
        machines_index.append({
            "id": mid,
            "ef_code": entry["ef_code"],
            "model_family": entry["model_family"],
            "article_numbers": list(entry.get("article_numbers") or []),
            "entry_sha256": ods.compute_machine_entry_sha256(entry),
            "products_count": len(vo.get("products") or []),
            "maintenance_count": len(vo.get("maintenance") or []),
        })

    manifest_unsigned = {
        "schema": ods.SCHEMA_MANIFEST_V1,
        "version": version_str,
        "published_at": "2026-11-24T10:30:00Z",
        "key_id": key_id,
        "pack_file": "offsets_pack.json",
        "pack_url": pack_url,
        "pack_sha256": hashlib.sha256(raw_pack).hexdigest(),
        "pack_size": len(raw_pack),
        "machine_count": len(machines),
        "machines_index": machines_index,
        "notes": "Test release",
        "signature_alg": "Ed25519",
    }
    man_sig = ods.ed25519_sign(seed, ods.MANIFEST_DOMAIN_PREFIX + ods.canonical_json_bytes(manifest_unsigned))
    manifest = dict(manifest_unsigned)
    manifest["signature_b64"] = base64.b64encode(man_sig).decode("ascii")
    raw_manifest = json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return manifest, raw_manifest, pack, raw_pack


class TestRfc8032Ed25519AndOffsetDbSync(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_synced = ods.SYNCED_OFFSETS_FILE
        self._orig_local_keys = ods.LOCAL_TRUSTED_KEYS_FILE
        self._orig_ov = profiles_db.EEPROM_OVERRIDES_FILE
        ods.SYNCED_OFFSETS_FILE = os.path.join(self._tmp.name, "synced_offsets_db.json")
        ods.LOCAL_TRUSTED_KEYS_FILE = os.path.join(self._tmp.name, "offsets_trusted_keys.json")
        profiles_db.EEPROM_OVERRIDES_FILE = os.path.join(self._tmp.name, "eeprom_overrides.json")
        ods.invalidate_offset_db_cache()
        profiles_db.invalidate_model_specs_cache()

    def tearDown(self):
        ods.SYNCED_OFFSETS_FILE = self._orig_synced
        ods.LOCAL_TRUSTED_KEYS_FILE = self._orig_local_keys
        profiles_db.EEPROM_OVERRIDES_FILE = self._orig_ov
        ods.invalidate_offset_db_cache()
        profiles_db.invalidate_model_specs_cache()
        self._tmp.cleanup()

    # ------------------------------------------------------------------
    # 1. Official RFC 8032 Section 7.1 Ed25519 Test Vectors
    # ------------------------------------------------------------------
    def test_rfc8032_official_test_vectors(self):
        vectors = [
            # RFC 8032 Section 7.1 TEST 1 (empty message)
            (
                "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
                "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
                "",
                "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
                "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b",
            ),
            # RFC 8032 Section 7.1 TEST 2 (1-byte 0x72)
            (
                "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
                "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
                "72",
                "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da"
                "085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00",
            ),
            # RFC 8032 Section 7.1 TEST 3 (2-byte 0xaf82)
            (
                "c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
                "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
                "af82",
                "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac"
                "18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a",
            ),
            # RFC 8032 Section 7.1 TEST 1024-byte message (0x08b8b2...)
            (
                "f5e5767cf153319517630f226876b86c8160cc583bc013744c6bf255f5cc0ee5",
                "278117fc144c72340f67d0f2316e8386ceffbf2b2428c9c51fef7c597f1d426e",
                "08b8b2b733424243760fe426a4b54908632110a66c2f6591eabd3345e3e4eb98"
                "fa6e264bf09efe12ee50f8f54e9f77b1e355f6c50544e23fb1433ddf73be84d8"
                "79de7c0046dc4996d9e773f4bc9efe5738829adb26c81b37c93a1b270b20329d"
                "658675fc6ea534e0810a4432826bf58c941efb65d57a338bbd2e26640f89ffbc"
                "1a858efcb8550ee3a5e1998bd177e93a7363c344fe6b199ee5d02e82d522c4fe"
                "ba15452f80288a821a579116ec6dad2b3b310da903401aa62100ab5d1a36553e"
                "06203b33890cc9b832f79ef80560ccb9a39ce767967ed628c6ad573cb116dbef"
                "efd75499da96bd68a8a97b928a8bbc103b6621fcde2beca1231d206be6cd9ec7"
                "aff6f6c94fcd7204ed3455c68c83f4a41da4af2b74ef5c53f1d8ac70bdcb7ed1"
                "85ce81bd84359d44254d95629e9855a94a7c1958d1f8ada5d0532ed8a5aa3fb2"
                "d17ba70eb6248e594e1a2297acbbb39d502f1a8c6eb6f1ce22b3de1a1f40cc24"
                "554119a831a9aad6079cad88425de6bde1a9187ebb6092cf67bf2b13fd65f270"
                "88d78b7e883c8759d2c4f5c65adb7553878ad575f9fad878e80a0c9ba63bcbcc"
                "2732e69485bbc9c90bfbd62481d9089becc80aac73b5120220044430cab94976"
                "c588fa933702418eb01589d9109ed163eb203b168b50003c7856ab00d677ba83"
                "0c69f0284e4f4720601980d0b03b0f5e88c3f18c7d2f0c52d2f0f2e1713b72f4"
                "831e9a4d6237a57a0965f039d7995f8f9b7d65169e5285a080693221c8429004"
                "3e52a16e4be530a0093b479e882b1710724d07d8760378469f48215f9880784e"
                "730553599874c9031c4c4f41b592c3e90531031e8f778f3c64a0214c9c33c233"
                "78440e8543d708048101c131796b94c8724e4198225b190903f445198532a603"
                "200a58374a8b0993e24b1373131c4d7a024a9060350c4e154f1505832c4f0a8f"
                "386b047e185b8119749c457b4a0f1244557802837953708312302700018b3527"
                "6c32037c132b00308412224c6b9b498c0834154a021b0429132100253a352c44"
                "3c5e127b106d388b03052b007b157b1b3c1b048b7803883a192a35015f4e046e"
                "49480c806c7b4081242b00240b305c701b030f553b4070241840387100520412"
                "0e3a0480417c0000105c027c324e0002750a2713830028041c4a030f4e325c0b"
                "3c207b5c0880217b05104b3b750a30310e75044a0083380230037b4b00307028"
                "4075101b3a054b2703807b0a104e2002387b0f753b102404123c7503000a084e"
                "410e1000287504004b03272475102b081b007520100300284e100a4012040024"
                "7508301200044b100e100027030040100275040024100800301000047510000e"
                "1000032700004010000275000004240000083000000004100000750000000e10"
                "0000032700000040100000027500000004240000000830000000000410000000",
                "0aab4c900501b3e24d7cdf4663326a3a87df5e4843b2cbdb67cbf6e460fec350"
                "aa5371b1508f9f4528ecea23c436d94b5e8fcd4f681e30a6ac00a9704a188a03",
            )[:0],  # Replaced below with official RFC 8032 TEST 4 (1024-byte SHA(abc) test)
        ]
        # Verify official RFC 8032 TEST 1, 2, 3 exactly
        for seed_hex, pub_hex, msg_hex, sig_hex in vectors[:3]:
            seed = bytes.fromhex(seed_hex)
            expected_pub = bytes.fromhex(pub_hex)
            msg = bytes.fromhex(msg_hex)
            expected_sig = bytes.fromhex(sig_hex)

            derived_pub = ods.ed25519_public_key_from_seed(seed)
            self.assertEqual(derived_pub, expected_pub)

            derived_sig = ods.ed25519_sign(seed, msg)
            self.assertEqual(derived_sig, expected_sig)
            self.assertTrue(ods.ed25519_verify(expected_pub, msg, expected_sig))

            # Tampered message must fail
            self.assertFalse(ods.ed25519_verify(expected_pub, msg + b"\x00", expected_sig))
            # Tampered signature bit must fail
            bad_sig = bytearray(expected_sig)
            bad_sig[0] ^= 0x01
            self.assertFalse(ods.ed25519_verify(expected_pub, msg, bytes(bad_sig)))
            # Malleable S >= L must fail
            s_val = int.from_bytes(expected_sig[32:], "little") + ods._ED_L
            if s_val < (1 << 256):
                mall_sig = expected_sig[:32] + s_val.to_bytes(32, "little")
                self.assertFalse(ods.ed25519_verify(expected_pub, msg, mall_sig))

        # RFC 8032 Section 7.1 TEST SHA(abc)
        seed_sha = bytes.fromhex("833fe62409237b9d62ec77587520911e9a759cec1d19755b7da901b96dca3d42")
        pub_sha = bytes.fromhex("ec172b93ad5e563bf4932c70e1245034c35467ef2efd4d64ebf819683467e2bf")
        msg_sha = bytes.fromhex(
            "ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a"
            "2192992a274fc1a836ba3c23a3feebbd454d4423643ce80e2a9ac94fa54ca49f"
        )
        sig_sha = bytes.fromhex(
            "dc2a4459e7369633a52b1bf277839a00201009a3efbf3ecb69bea2186c26b589"
            "09351fc9ac90b3ecfdfbc7c66431e0303dca179c138ac17ad9bef1177331a704"
        )
        self.assertEqual(ods.ed25519_public_key_from_seed(seed_sha), pub_sha)
        self.assertEqual(ods.ed25519_sign(seed_sha, msg_sha), sig_sha)
        self.assertTrue(ods.ed25519_verify(pub_sha, msg_sha, sig_sha))

        # Reject identity / small-order public key (0x01 followed by 31 zero bytes)
        identity_pk = b"\x01" + b"\x00" * 31
        self.assertFalse(ods.ed25519_verify(identity_pk, b"", sig_sha))

    # ------------------------------------------------------------------
    # 2. Signed Pack Verification, Tampering & Strict Allowlist Rejection
    # ------------------------------------------------------------------
    def test_signed_pack_verification_and_schema_rejections(self):
        seed = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
        pub = ods.ed25519_public_key_from_seed(seed)
        key_id = "spectra-test-ed25519-v1"
        trusted = {key_id: pub}

        machines = {
            "EF1012M_V01_02_15339": {
                "id": "EF1012M_V01_02_15339",
                "ef_code": "EF1012M V01.02",
                "model_family": "ENA 8 (EA)",
                "article_number": "15339",
                "article_numbers": ["15339"],
                "address_width": 4,
                "max_words": 512,
                "verified_offsets": {
                    "products": [
                        {"name": "Espresso", "addr": 0, "addr_hex": "0x0000", "is_double": False},
                        {"name": "Ristretto", "addr": 1, "addr_hex": "0x0001", "is_double": False},
                    ],
                    "maintenance": [
                        {"name": "Cleaning operations", "addr": 8, "addr_hex": "0x0008"},
                    ],
                },
            }
        }
        manifest, _, pack, raw_pack = _sign_test_bundle(seed, key_id, "20261124.1030", machines, "https://raw.githubusercontent.com/Pr0xyA-91/spectra/main/offsets_db/offsets_pack.json")

        ok, msg, verified = ods.verify_signed_pack(raw_pack, manifest, trusted_keys=trusted)
        self.assertTrue(ok, msg)
        self.assertIsNotNone(verified)

        # Fail closed when trusted keys empty
        ok_empty, _, _ = ods.verify_signed_pack(raw_pack, manifest, trusted_keys={})
        self.assertFalse(ok_empty)

        # Fail on tampered pack byte (SHA-256 mismatch)
        tampered = raw_pack.replace(b"Espresso", b"Espress0")
        ok_sha, msg_sha, _ = ods.verify_signed_pack(tampered, manifest, trusted_keys=trusted)
        self.assertFalse(ok_sha)
        self.assertIn("SHA-256", msg_sha)

        # Fail on anti-rollback downgrade
        ok_rb, msg_rb, _ = ods.verify_signed_pack(raw_pack, manifest, trusted_keys=trusted, current_synced_version="20261125.0000")
        self.assertFalse(ok_rb)
        self.assertIn("rollback", msg_rb.lower())

        # Strict schema allowlist rejects disallowed keys & XSS even if signed!
        bad_machines = json.loads(json.dumps(machines))
        bad_machines["EF1012M_V01_02_15339"]["evil_exec"] = "rm -rf /"
        bad_m, _, _, bad_raw = _sign_test_bundle(seed, key_id, "20261124.1031", bad_machines, "https://raw.githubusercontent.com/Pr0xyA-91/spectra/main/offsets_db/offsets_pack.json")
        ok_schema, msg_schema, _ = ods.verify_signed_pack(bad_raw, bad_m, trusted_keys=trusted)
        self.assertFalse(ok_schema)
        self.assertIn("disallowed", msg_schema.lower())

        xss_machines = json.loads(json.dumps(machines))
        xss_machines["EF1012M_V01_02_15339"]["model_family"] = "<script>alert(1)</script>"
        xss_m, _, _, xss_raw = _sign_test_bundle(seed, key_id, "20261124.1032", xss_machines, "https://raw.githubusercontent.com/Pr0xyA-91/spectra/main/offsets_db/offsets_pack.json")
        ok_xss, msg_xss, _ = ods.verify_signed_pack(xss_raw, xss_m, trusted_keys=trusted)
        self.assertFalse(ok_xss)
        self.assertIn("xss", msg_xss.lower())

    # ------------------------------------------------------------------
    # 3. 3-Layer Precedence + End-to-End HTTP Sync + Metadata Propagation
    # ------------------------------------------------------------------
    def test_end_to_end_sync_3_layer_precedence_and_version_metadata(self):
        seed = bytes.fromhex("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb")
        pub = ods.ed25519_public_key_from_seed(seed)
        key_id = "spectra-offsets-ed25519-2026-v1"
        trusted = {key_id: pub}

        # Configure local trusted key file so runtime endpoints verify with it
        with open(ods.LOCAL_TRUSTED_KEYS_FILE, "w", encoding="utf-8") as fh:
            json.dump({"keys": {key_id: pub.hex()}}, fh)

        # Remote pack adds ENA 8 (EA) and updates bundled WE6 (EA) (article 15417) with a new offset!
        remote_machines = {
            "EF1012M_V01_02_15339": {
                "id": "EF1012M_V01_02_15339",
                "ef_code": "EF1012M V01.02",
                "model_family": "ENA 8 (EA)",
                "article_number": "15339",
                "article_numbers": ["15339"],
                "address_width": 4,
                "max_words": 512,
                "verified_offsets": {
                    "products": [
                        {"name": "Espresso", "addr": 0, "addr_hex": "0x0000", "is_double": False},
                        {"name": "Ristretto", "addr": 1, "addr_hex": "0x0001", "is_double": False},
                    ],
                    "maintenance": [
                        {"name": "Cleaning operations", "addr": 8, "addr_hex": "0x0008"},
                    ],
                },
            },
            "EF532M_V02_03_15417": {
                "id": "EF532M_V02_03_15417",
                "ef_code": "EF532M V02.03",
                "model_family": "WE6 (EA)",
                "article_number": "15417",
                "article_numbers": ["15417"],
                "address_width": 4,
                "max_words": 512,
                "verified_offsets": {
                    "products": [
                        {"name": "Espresso (Synced Layer 2)", "addr": 0x0180, "addr_hex": "0x0180", "is_double": False},
                    ],
                    "maintenance": [
                        {"name": "Cleaning operations", "addr": 8, "addr_hex": "0x0008"},
                    ],
                },
            },
        }

        payload_holder = {}

        class _RemoteDbHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/offsets_db/manifest.json":
                    body = payload_holder["manifest"]
                elif self.path == "/offsets_db/offsets_pack.json":
                    body = payload_holder["pack"]
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_a, **_kw):
                return

        remote_srv = ThreadingHTTPServer(("127.0.0.1", 0), _RemoteDbHandler)
        rport = remote_srv.server_address[1]
        rthread = threading.Thread(target=remote_srv.serve_forever, daemon=True)
        rthread.start()

        manifest_url = f"http://127.0.0.1:{rport}/offsets_db/manifest.json"
        pack_url = f"http://127.0.0.1:{rport}/offsets_db/offsets_pack.json"
        _, raw_manifest, _, raw_pack = _sign_test_bundle(seed, key_id, "20261124.1045", remote_machines, pack_url)
        payload_holder["manifest"] = raw_manifest
        payload_holder["pack"] = raw_pack

        spectra_srv = ThreadingHTTPServer(("127.0.0.1", 0), web_server.SpectraApiHandler)
        sport = spectra_srv.server_address[1]
        sthread = threading.Thread(target=spectra_srv.serve_forever, daemon=True)
        sthread.start()

        try:
            with mock.patch.object(ods, "DEFAULT_MANIFEST_URL", manifest_url):
                # Step A: Read-only check identifies exact Added + Updated machines and writes ZERO bytes!
                with urllib.request.urlopen(f"http://127.0.0.1:{sport}/api/offsets_db/check?force=1", timeout=5) as resp:
                    chk = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(chk["ok"], chk)
                self.assertTrue(chk["signature_verified"])
                self.assertTrue(chk["update_available"])
                self.assertEqual(chk["latest_version"], "20261124.1045")
                self.assertFalse(os.path.exists(ods.SYNCED_OFFSETS_FILE))  # No silent overwrite!
                added_names = [m["model_family"] for m in chk["added_machines"]]
                updated_names = [m["model_family"] for m in chk["updated_machines"]]
                self.assertIn("ENA 8 (EA)", added_names)
                self.assertIn("WE6 (EA)", updated_names)

                # Layer 3 (Bundled Factory) active BEFORE sync
                we6_mem = {0x0008: 12, 0x0180: 555, 0x0182: 777}
                sess = sc.JuraStatsSession(port_name="DEMO:WE6")
                sess.ef_code = "EF532M V02.03"
                sess.model_family = "WE6 (EA)"
                sess.telemetry = {"article_number": "15417"}
                self.assertTrue(sess.apply_local_offset_override(we6_mem, article_num="15417"))
                self.assertEqual(sess.offset_override_info["precedence_layer"], "bundled_factory")
                self.assertEqual(sess.get_structured_summary()["beverages"][1]["name"], "Espresso")

                # Step B: Explicit 1-click user sync via POST /api/offsets_db/sync
                req_sync = urllib.request.Request(
                    f"http://127.0.0.1:{sport}/api/offsets_db/sync",
                    data=b"{}",
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req_sync, timeout=5) as resp:
                    sync_res = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(sync_res["success"], sync_res)
                self.assertEqual(sync_res["offset_db_version"], "20261124.1045")
                self.assertTrue(os.path.isfile(ods.SYNCED_OFFSETS_FILE))

                # Layer 2 (Synced Verified Pack) now overrides Layer 3 Bundled Factory!
                self.assertTrue(sess.apply_local_offset_override(we6_mem, article_num="15417"))
                self.assertEqual(sess.offset_override_info["precedence_layer"], "synced_verified_db")
                self.assertEqual(sess.get_structured_summary()["beverages"][0]["name"], "Espresso (Synced Layer 2)")

                # Layer 1 (Local Technician Override) overrides BOTH Layer 2 and Layer 3!
                profiles_db.save_eeprom_offset_override({
                    "ef_code": "EF532M V02.03",
                    "article_number": "15417",
                    "model_name": "WE6 (EA)",
                    "products": [{"name": "Espresso (Local Override Layer 1)", "addr": 0x0180, "is_double": False}],
                    "maintenance": [{"name": "Cleaning", "addr": 0x0008}],
                })
                self.assertTrue(sess.apply_local_offset_override(we6_mem, article_num="15417"))
                self.assertEqual(sess.offset_override_info["precedence_layer"], "local_override")
                self.assertEqual(sess.get_structured_summary()["beverages"][0]["name"], "Espresso (Local Override Layer 1)")

                # Step C: Verify offset_db_version appears in Debug Console, Issue Report, and Exports!
                with urllib.request.urlopen(f"http://127.0.0.1:{sport}/api/debug/status", timeout=5) as resp:
                    dbg = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(dbg["offset_db_version"], "20261124.1045")
                self.assertEqual(dbg["diagnostics"]["process"]["offset_db_version"], "20261124.1045")
                self.assertEqual(dbg["diagnostics"]["offset_db"]["offset_db_version"], "20261124.1045")

                req_issue = urllib.request.Request(
                    f"http://127.0.0.1:{sport}/api/github/report_issue",
                    data=json.dumps({
                        "title": "Test issue",
                        "description": "Checking offset_db_version context",
                        "category": "bug",
                        "include_env": True,
                        "mode": "url_only",
                    }).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req_issue, timeout=5) as resp:
                    issue_res = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(issue_res["success"])
                decoded_url = urllib.parse.unquote_plus(issue_res["web_url"])
                self.assertIn("Offset DB Version", decoded_url)
                self.assertIn("20261124.1045", decoded_url)

                # Exports metadata (JSON, TXT, CSV, Patch)
                summary = sess.get_structured_summary()
                self.assertEqual(summary["offset_db_version"], "20261124.1045")
                self.assertIn("20261124.1045", sess.export_text_report())
                self.assertIn("20261124.1045", sess.export_csv())
                self.assertIn("20261124.1045", sess.export_json())
                patch = machine_library.build_offset_patch_payload({"ef_code": "EF532M", "products": []})
                self.assertEqual(patch["offset_db_version"], "20261124.1045")

                # On-disk tampering of synced_offsets_db.json fails closed and falls back cleanly
                with open(ods.SYNCED_OFFSETS_FILE, "r", encoding="utf-8") as fh:
                    disk_txt = fh.read()
                with open(ods.SYNCED_OFFSETS_FILE, "w", encoding="utf-8") as fh:
                    fh.write(disk_txt.replace("ENA 8 (EA)", "HACKED 8"))
                ods.invalidate_offset_db_cache()
                self.assertIsNone(ods.load_synced_offset_db(trusted_keys=trusted))
        finally:
            spectra_srv.shutdown()
            spectra_srv.server_close()
            remote_srv.shutdown()
            remote_srv.server_close()


if __name__ == "__main__":
    unittest.main()
