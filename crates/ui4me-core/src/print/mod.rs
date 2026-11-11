//! Printing and paged export (1.0 F1002).
//!
//! The owner thread paginates the document and renders each page at the job's resolution into a
//! zlib-compressed RGB image ([`Page`]); a job holds at most [`MAX_JOB_BYTES`] of compressed
//! pages. Those pages are then written as a PDF ([`pdf`]: one image per page, deterministic
//! bytes, no fonts, no metadata timestamps), saved by `export_pdf`, or printed by a worker
//! thread: Windows shows the system print dialog (`PrintDlgExW`) and draws the pages with GDI;
//! Linux sends the PDF through the xdg-desktop-portal Print interface, whose dialog is the
//! desktop's own. The outcome arrives as one `print` event; nothing is retried behind the app.
//! The text of an exported PDF is an image (not searchable or selectable).

use miniz_oxide::deflate::compress_to_vec_zlib;

#[cfg(all(target_os = "linux", feature = "native"))]
pub mod linux;
#[cfg(all(target_os = "windows", feature = "native"))]
pub mod windows;

/// Compressed bytes of all pages of one job.
pub const MAX_JOB_BYTES: usize = 512 * 1024 * 1024;
/// Resolution bounds of rendered pages.
pub const MIN_DPI: f32 = 36.0;
pub const MAX_DPI: f32 = 600.0;

/// One rendered page: device pixel size, the page box in CSS px, zlib-compressed RGB rows.
#[derive(Clone, Debug)]
pub struct Page {
    pub width_px: u32,
    pub height_px: u32,
    pub width_css: f32,
    pub height_css: f32,
    pub zlib_rgb: Vec<u8>,
}

impl Page {
    /// From un-premultiplied, opaque RGBA rows.
    pub fn from_rgba(
        width_px: u32,
        height_px: u32,
        width_css: f32,
        height_css: f32,
        rgba: &[u8],
    ) -> Page {
        let rgb: Vec<u8> = rgba
            .chunks_exact(4)
            .flat_map(|p| [p[0], p[1], p[2]])
            .collect();
        Page {
            width_px,
            height_px,
            width_css,
            height_css,
            zlib_rgb: compress_to_vec_zlib(&rgb, 6),
        }
    }
    /// The RGB rows again (for GDI).
    #[cfg_attr(not(target_os = "windows"), allow(dead_code))]
    pub fn rgb(&self) -> Result<Vec<u8>, String> {
        miniz_oxide::inflate::decompress_to_vec_zlib_with_limit(
            &self.zlib_rgb,
            self.width_px as usize * self.height_px as usize * 3,
        )
        .map_err(|e| format!("page image: {e:?}"))
    }
}

/// A PDF of `pages` (one full-page image each; points = CSS px × 0.75).
pub fn pdf(pages: &[Page], title: &str) -> Vec<u8> {
    let mut out: Vec<u8> = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n".to_vec();
    let mut offsets: Vec<usize> = Vec::new();
    let obj = |out: &mut Vec<u8>, offsets: &mut Vec<usize>, body: &[u8]| {
        offsets.push(out.len());
        out.extend_from_slice(format!("{} 0 obj\n", offsets.len()).as_bytes());
        out.extend_from_slice(body);
        out.extend_from_slice(b"\nendobj\n");
    };
    // 1 catalog, 2 pages, 3 info, then 3 objects per page: page, content, image.
    let kids: Vec<String> = (0..pages.len())
        .map(|i| format!("{} 0 R", 4 + i * 3))
        .collect();
    obj(&mut out, &mut offsets, b"<< /Type /Catalog /Pages 2 0 R >>");
    obj(
        &mut out,
        &mut offsets,
        format!(
            "<< /Type /Pages /Kids [{}] /Count {} >>",
            kids.join(" "),
            pages.len()
        )
        .as_bytes(),
    );
    let escaped: String = title
        .chars()
        .filter(|c| c.is_ascii() && !c.is_ascii_control())
        .flat_map(|c| match c {
            '(' | ')' | '\\' => vec!['\\', c],
            _ => vec![c],
        })
        .collect();
    obj(
        &mut out,
        &mut offsets,
        format!("<< /Producer (UI4ME Core) /Title ({escaped}) >>").as_bytes(),
    );
    for (i, p) in pages.iter().enumerate() {
        let (w, h) = (p.width_css * 0.75, p.height_css * 0.75);
        let n = 4 + i * 3;
        obj(
            &mut out,
            &mut offsets,
            format!(
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w:.3} {h:.3}] /Contents {} 0 R /Resources << /XObject << /Im0 {} 0 R >> >> >>",
                n + 1,
                n + 2
            )
            .as_bytes(),
        );
        let content = format!("q {w:.3} 0 0 {h:.3} 0 0 cm /Im0 Do Q");
        obj(
            &mut out,
            &mut offsets,
            format!(
                "<< /Length {} >>\nstream\n{content}\nendstream",
                content.len()
            )
            .as_bytes(),
        );
        let mut img = format!(
            "<< /Type /XObject /Subtype /Image /Width {} /Height {} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length {} >>\nstream\n",
            p.width_px,
            p.height_px,
            p.zlib_rgb.len()
        )
        .into_bytes();
        img.extend_from_slice(&p.zlib_rgb);
        img.extend_from_slice(b"\nendstream");
        obj(&mut out, &mut offsets, &img);
    }
    let xref = out.len();
    out.extend_from_slice(
        format!("xref\n0 {}\n0000000000 65535 f \n", offsets.len() + 1).as_bytes(),
    );
    for o in &offsets {
        out.extend_from_slice(format!("{o:010} 00000 n \n").as_bytes());
    }
    out.extend_from_slice(
        format!(
            "trailer\n<< /Size {} /Root 1 0 R /Info 3 0 R >>\nstartxref\n{xref}\n%%EOF\n",
            offsets.len() + 1
        )
        .as_bytes(),
    );
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pdf_is_deterministic_and_well_formed() {
        let rgba = vec![255u8; 4 * 4 * 4];
        let page = Page::from_rgba(4, 4, 96.0, 96.0, &rgba);
        let a = pdf(&[page.clone(), page.clone()], "Report (1)");
        assert_eq!(a, pdf(&[page.clone(), page], "Report (1)"), "deterministic");
        let s = String::from_utf8_lossy(&a);
        assert!(s.starts_with("%PDF-1.4"));
        assert!(s.contains("/Count 2") && s.contains("/MediaBox [0 0 72.000 72.000]"));
        assert!(s.contains("/Title (Report \\(1\\))"));
        // Every xref offset points at its object.
        let xref = s.rfind("xref\n").unwrap();
        for (i, line) in s[xref..].lines().skip(3).take(9).enumerate() {
            let off: usize = line[..10].parse().unwrap();
            assert!(
                s[off..].starts_with(&format!("{} 0 obj", i + 1)),
                "object {}",
                i + 1
            );
        }
        assert!(s.ends_with("%%EOF\n"));
    }

    #[test]
    fn pages_round_trip() {
        let rgba: Vec<u8> = (0..16).flat_map(|i| [i as u8, 2, 3, 255]).collect();
        let p = Page::from_rgba(4, 4, 4.0, 4.0, &rgba);
        let rgb = p.rgb().unwrap();
        assert_eq!(rgb.len(), 48);
        assert_eq!(&rgb[3..6], &[1, 2, 3]);
    }
}
