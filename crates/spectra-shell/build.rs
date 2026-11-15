use std::env;
use std::fs;
use std::path::PathBuf;
use std::process::Command;

fn main() {
    let target_os = env::var("CARGO_CFG_TARGET_OS").unwrap_or_default();
    if target_os != "windows" {
        return;
    }

    let manifest_dir = PathBuf::from(env::var("CARGO_MANIFEST_DIR").unwrap());
    let icon_path = manifest_dir.join("..").join("..").join("icon.ico");
    println!("cargo:rerun-if-changed={}", icon_path.display());

    if !icon_path.exists() {
        return;
    }

    let out_dir = PathBuf::from(env::var("OUT_DIR").unwrap());
    let rc_path = out_dir.join("spectra_shell_icon.rc");
    let res_path = out_dir.join("spectra_shell_icon.res");

    let icon_escaped = icon_path
        .canonicalize()
        .unwrap_or(icon_path)
        .to_string_lossy()
        .replace('\\', "/");
    let rc_content = format!("1 ICON \"{}\"\n", icon_escaped);
    if fs::write(&rc_path, rc_content).is_err() {
        return;
    }

    let rc_ok = Command::new("llvm-rc")
        .arg("/fo")
        .arg(&res_path)
        .arg(&rc_path)
        .status()
        .map(|s| s.success())
        .unwrap_or(false);

    if rc_ok && res_path.exists() {
        println!("cargo:rustc-link-arg-bins={}", res_path.display());
    }
}
