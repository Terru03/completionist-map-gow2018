"""Promote the approved Discord chest ZIP without rebuilding its installed files."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
TEST_SHA256 = "0c62c03661e47e8934586bdd9e2fd5f4dd6816be6ebfa2da13f1d832b87f3117"
INSTALLERS = ("Install.bat", "Uninstall.bat", "scripts/install.ps1", "scripts/uninstall.ps1")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def promote(source, output):
    source = source.resolve()
    output = output.resolve()
    if digest(source.read_bytes()) != TEST_SHA256:
        raise ValueError("Source does not match the player-tested Discord ZIP.")
    if output.exists():
        raise FileExistsError("Keep existing release ZIPs; choose a new output path.")
    with ZipFile(source) as archive:
        if archive.testzip() is not None:
            raise ValueError("Source ZIP failed its CRC check.")
        entries = archive.infolist()
        files = {entry.filename: archive.read(entry) for entry in entries}
    if len(entries) != len(files):
        raise ValueError("Duplicate ZIP entry names.")
    manifest = json.loads(files["manifest.json"])
    if manifest["version"] != "1.0.4-chest-tracking-test" or len(manifest["files"]) != 20:
        raise ValueError("Unexpected tested package manifest.")
    for name, record in manifest["files"].items():
        payload = files[name]
        if len(payload) != record["size"] or digest(payload) != record["sha256"]:
            raise ValueError(f"Tested payload fails its manifest: {name}")

    spec = importlib.util.spec_from_file_location("nexus_package", ROOT / "tools/build-nexus-package.py")
    package = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(package)
    if package.VERSION != "1.0.4":
        raise ValueError("The package builder version must remain 1.0.4.")
    manifest["name"] = "God of War Completionist Map"
    manifest["version"] = "1.0.4"
    replacements = {
        "manifest.json": (json.dumps(manifest, indent=2) + "\n").encode("utf-8"),
        "README.txt": (package.README_TXT.strip() + "\n").encode("utf-8"),
        "CHANGELOG.txt": (ROOT / "docs/releases/v1.0.4-release-notes.txt").read_bytes(),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w") as archive:
        for entry in entries:
            if entry.filename != "CHEST-TRACKING-TEST.txt":
                archive.writestr(entry, replacements.get(entry.filename, files[entry.filename]))
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        for name in (*manifest["files"], *INSTALLERS):
            assert archive.read(name) == files[name], name
        assert set(archive.namelist()) == set(files) - {"CHEST-TRACKING-TEST.txt"}
        assert json.loads(archive.read("manifest.json"))["version"] == "1.0.4"
        for name in ("README.txt", "CHANGELOG.txt"):
            text = archive.read(name).decode("utf-8").lower()
            assert "test build" not in text and "validation is pending" not in text
    result = {
        "version": "1.0.4",
        "filename": output.name,
        "size": output.stat().st_size,
        "sha256": digest(output.read_bytes()),
        "tested_zip_sha256": TEST_SHA256,
        "installed_payloads_unchanged": len(manifest["files"]),
        "installer_files_unchanged": len(INSTALLERS),
        "metadata_changed": sorted(replacements),
        "removed_test_note": "CHEST-TRACKING-TEST.txt",
        "files": manifest["files"],
    }
    output.with_suffix(".sha256.txt").write_text(f"{result['sha256']}  {output.name}\n", encoding="utf-8")
    output.with_suffix(".provenance.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = promote(args.source, args.output)
    print(json.dumps({key: value for key, value in result.items() if key != "files"}, indent=2))
