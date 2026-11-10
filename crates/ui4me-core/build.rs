fn main() {
    println!("cargo:rerun-if-env-changed=UI4ME_SOURCE_ID");
    println!("cargo:rerun-if-env-changed=UI4ME_GIT_REVISION");
    println!(
        "cargo:rustc-env=UI4ME_BUILD_TARGET={}",
        std::env::var("TARGET").unwrap_or_default()
    );
    println!(
        "cargo:rustc-env=UI4ME_SOURCE_ID={}",
        std::env::var("UI4ME_SOURCE_ID").unwrap_or_else(|_| "unidentified".into())
    );
    println!(
        "cargo:rustc-env=UI4ME_GIT_REVISION={}",
        std::env::var("UI4ME_GIT_REVISION").unwrap_or_else(|_| "uncommitted".into())
    );
}
