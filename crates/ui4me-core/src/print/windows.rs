//! Native printing on Windows (1.0 F1002): the system print dialog (`PrintDlgExW`, owned by the
//! window) and GDI. Each page image is scaled to fit the printable area (aspect kept, centred)
//! with `StretchDIBits`. Runs on a worker thread (COM apartment of its own); the outcome is one
//! `print` event.

use super::Page;
use serde_json::json;
use windows_sys::Win32::Foundation::{GlobalFree, HWND};
use windows_sys::Win32::Graphics::Gdi::{
    DeleteDC, GetDeviceCaps, StretchDIBits, BITMAPINFO, BITMAPINFOHEADER, BI_RGB, DIB_RGB_COLORS,
    HDC, HORZRES, LOGPIXELSX, LOGPIXELSY, SRCCOPY, VERTRES,
};
use windows_sys::Win32::Storage::Xps::{AbortDoc, EndDoc, EndPage, StartDocW, StartPage, DOCINFOW};
use windows_sys::Win32::System::Com::{CoInitializeEx, CoUninitialize, COINIT_APARTMENTTHREADED};
use windows_sys::Win32::UI::Controls::Dialogs::{
    PrintDlgExW, PD_NOCURRENTPAGE, PD_NOPAGENUMS, PD_NOSELECTION, PD_RESULT_CANCEL,
    PD_RESULT_PRINT, PD_RETURNDC, PD_USEDEVMODECOPIESANDCOLLATE, PRINTDLGEXW, START_PAGE_GENERAL,
};

/// Print `pages` with `owner` as the dialog's parent; returns the `print` event body.
pub fn print(owner: isize, pages: &[Page], title: &str) -> serde_json::Value {
    // SAFETY: COM for the dialog on this worker thread; balanced below.
    let com = unsafe { CoInitializeEx(std::ptr::null(), COINIT_APARTMENTTHREADED as u32) };
    let out = run(owner as HWND, pages, title);
    if com >= 0 {
        unsafe { CoUninitialize() };
    }
    out
}

fn run(owner: HWND, pages: &[Page], title: &str) -> serde_json::Value {
    // SAFETY: a zeroed PRINTDLGEXW with its size and flags is the documented initial state.
    let mut pd: PRINTDLGEXW = unsafe { std::mem::zeroed() };
    pd.lStructSize = std::mem::size_of::<PRINTDLGEXW>() as u32;
    pd.hwndOwner = owner;
    pd.Flags = PD_RETURNDC
        | PD_NOPAGENUMS
        | PD_NOSELECTION
        | PD_NOCURRENTPAGE
        | PD_USEDEVMODECOPIESANDCOLLATE;
    pd.nStartPage = START_PAGE_GENERAL;
    pd.nCopies = 1;
    // SAFETY: `pd` is initialised; the dialog fills the handles we free below.
    let hr = unsafe { PrintDlgExW(&mut pd) };
    let free = |pd: &PRINTDLGEXW| unsafe {
        if !pd.hDevMode.is_null() {
            GlobalFree(pd.hDevMode);
        }
        if !pd.hDevNames.is_null() {
            GlobalFree(pd.hDevNames);
        }
    };
    if hr < 0 {
        free(&pd);
        return json!({"status": "failed", "reason": format!("PrintDlgEx failed (0x{:08X})", hr as u32)});
    }
    if pd.dwResultAction == PD_RESULT_CANCEL || pd.dwResultAction != PD_RESULT_PRINT {
        free(&pd);
        if !pd.hDC.is_null() {
            unsafe { DeleteDC(pd.hDC) };
        }
        return json!({"status": "cancelled"});
    }
    let dc = pd.hDC;
    let result = draw(dc, pages, title);
    unsafe { DeleteDC(dc) };
    free(&pd);
    match result {
        Ok(()) => json!({"status": "printed"}),
        Err(reason) => json!({"status": "failed", "reason": reason}),
    }
}

fn draw(dc: HDC, pages: &[Page], title: &str) -> Result<(), String> {
    let name: Vec<u16> = if title.is_empty() {
        "UI4ME document"
    } else {
        title
    }
    .encode_utf16()
    .chain(std::iter::once(0))
    .collect();
    // SAFETY: a zeroed DOCINFOW with its size and name is valid.
    let mut di: DOCINFOW = unsafe { std::mem::zeroed() };
    di.cbSize = std::mem::size_of::<DOCINFOW>() as i32;
    di.lpszDocName = name.as_ptr();
    if unsafe { StartDocW(dc, &di) } <= 0 {
        return Err("StartDoc failed (printer unavailable or the output was cancelled)".into());
    }
    let (hres, vres, dpx, dpy) = unsafe {
        (
            GetDeviceCaps(dc, HORZRES as i32),
            GetDeviceCaps(dc, VERTRES as i32),
            GetDeviceCaps(dc, LOGPIXELSX as i32),
            GetDeviceCaps(dc, LOGPIXELSY as i32),
        )
    };
    for (i, p) in pages.iter().enumerate() {
        let rgb = p.rgb().inspect_err(|_| unsafe {
            AbortDoc(dc);
        })?;
        // BGR rows, each padded to 4 bytes, top-down.
        let stride = (p.width_px as usize * 3).div_ceil(4) * 4;
        let mut bgr = vec![0u8; stride * p.height_px as usize];
        for y in 0..p.height_px as usize {
            for x in 0..p.width_px as usize {
                let s = (y * p.width_px as usize + x) * 3;
                let d = y * stride + x * 3;
                bgr[d] = rgb[s + 2];
                bgr[d + 1] = rgb[s + 1];
                bgr[d + 2] = rgb[s];
            }
        }
        // The page box at the printer's resolution, fitted into the printable area.
        let want_w = f64::from(p.width_css) / 96.0 * f64::from(dpx);
        let want_h = f64::from(p.height_css) / 96.0 * f64::from(dpy);
        let k = (f64::from(hres) / want_w)
            .min(f64::from(vres) / want_h)
            .min(1.0);
        let (w, h) = ((want_w * k) as i32, (want_h * k) as i32);
        let (x, y) = ((hres - w) / 2, (vres - h) / 2);
        // SAFETY: a zeroed BITMAPINFO with its header filled describes `bgr`.
        let mut bmi: BITMAPINFO = unsafe { std::mem::zeroed() };
        bmi.bmiHeader = BITMAPINFOHEADER {
            biSize: std::mem::size_of::<BITMAPINFOHEADER>() as u32,
            biWidth: p.width_px as i32,
            biHeight: -(p.height_px as i32),
            biPlanes: 1,
            biBitCount: 24,
            biCompression: BI_RGB,
            ..unsafe { std::mem::zeroed() }
        };
        let ok = unsafe {
            StartPage(dc) > 0
                && StretchDIBits(
                    dc,
                    x,
                    y,
                    w,
                    h,
                    0,
                    0,
                    p.width_px as i32,
                    p.height_px as i32,
                    bgr.as_ptr().cast(),
                    &bmi,
                    DIB_RGB_COLORS,
                    SRCCOPY,
                ) != 0
                && EndPage(dc) > 0
        };
        if !ok {
            unsafe { AbortDoc(dc) };
            return Err(format!("printing page {} failed", i + 1));
        }
    }
    if unsafe { EndDoc(dc) } <= 0 {
        return Err("EndDoc failed".into());
    }
    Ok(())
}
