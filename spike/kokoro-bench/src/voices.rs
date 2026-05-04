//! Loader for Kokoro voices-v1.0.bin (numpy `np.savez` archive of float32 [510,1,256] tensors).

use anyhow::{bail, Context, Result};
use byteorder::{LittleEndian, ReadBytesExt};
use std::collections::HashMap;
use std::fs::File;
use std::io::{BufReader, Read};
use std::path::Path;

/// In-memory store of all voices from voices-v1.0.bin.
/// Each value is a flat Vec<f32> of length 510 * 1 * 256 = 130_560.
pub struct Voices {
    pub voices: HashMap<String, Vec<f32>>,
}

impl Voices {
    pub fn load(path: &Path) -> Result<Self> {
        let file = File::open(path).with_context(|| format!("open {}", path.display()))?;
        let mut zip = zip::ZipArchive::new(file).context("voices file is not a valid zip/npz")?;
        let mut voices = HashMap::new();
        for i in 0..zip.len() {
            let mut entry = zip.by_index(i)?;
            let name = entry.name().to_string();
            let key = name.trim_end_matches(".npy").to_string();
            let mut bytes = Vec::with_capacity(entry.size() as usize);
            entry.read_to_end(&mut bytes)?;
            let arr = parse_npy_f32(&bytes)
                .with_context(|| format!("parse npy entry {name}"))?;
            voices.insert(key, arr);
        }
        Ok(Self { voices })
    }

    /// Slice the style vector at `token_count`, returning a flat [1, 256] = 256 f32.
    /// Matches Python: `voice = voice[len(tokens)]` on shape (510, 1, 256).
    pub fn style_for(&self, name: &str, token_count: usize) -> Result<&[f32]> {
        let arr = self
            .voices
            .get(name)
            .with_context(|| format!("voice {name} not found"))?;
        // Layout: [510, 1, 256] = 510 rows of 256 floats (the middle dim is 1).
        let row_size = 256;
        let rows = arr.len() / row_size;
        if token_count >= rows {
            bail!(
                "token_count {} exceeds voice rows {} for voice {}",
                token_count,
                rows,
                name
            );
        }
        let start = token_count * row_size;
        Ok(&arr[start..start + row_size])
    }
}

/// Minimal `.npy` parser for float32 arrays in C order.
fn parse_npy_f32(bytes: &[u8]) -> Result<Vec<f32>> {
    if bytes.len() < 10 || &bytes[0..6] != b"\x93NUMPY" {
        bail!("not a npy file (bad magic)");
    }
    let major = bytes[6];
    let _minor = bytes[7];
    let mut cursor = std::io::Cursor::new(&bytes[8..]);
    let header_len = if major == 1 {
        cursor.read_u16::<LittleEndian>()? as usize
    } else {
        cursor.read_u32::<LittleEndian>()? as usize
    };
    let header_start = if major == 1 { 10 } else { 12 };
    let header = std::str::from_utf8(&bytes[header_start..header_start + header_len])
        .context("npy header not utf-8")?;
    if !header.contains("'<f4'") && !header.contains("'float32'") {
        bail!("npy dtype not float32: {header}");
    }
    if header.contains("'fortran_order': True") {
        bail!("fortran-order npy not supported");
    }
    let data_start = header_start + header_len;
    let data = &bytes[data_start..];
    if data.len() % 4 != 0 {
        bail!("npy float32 data length {} not multiple of 4", data.len());
    }
    let count = data.len() / 4;
    let mut out = Vec::with_capacity(count);
    let mut rdr = BufReader::new(data);
    for _ in 0..count {
        out.push(rdr.read_f32::<LittleEndian>()?);
    }
    Ok(out)
}
