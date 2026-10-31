//! `sedge` — command-line front end for shannon-edge.

use shannon_edge::{
    compress_with_dictionary, decompress_with_dictionary, Options, DEFAULT_BLOCK_SIZE,
    MAX_MEM_BITS, MIN_MEM_BITS,
};
use std::fs;
use std::io::{self, Read, Write};
use std::path::Path;
use std::process::ExitCode;
use std::time::Instant;

const USAGE: &str = "\
sedge — lossless compression by prediction (shannon-edge)

USAGE:
    sedge compress   <input> [-o <output>] [-D <dict>] [-m <level>] [-b <MiB>] [-t <n>] [-f]
    sedge decompress <input> [-o <output>] [-D <dict>] [-t <n>] [-f]
    sedge bench      <file>... [-D <dict>] [-m <level>] [-b <MiB>] [-t <n>]

COMMANDS:
    compress, c      Compress <input> (default output: <input>.sedge)
    decompress, d    Decompress <input> (default output: <input> without .sedge)
    bench, b         Compress + decompress in memory, verify, report ratio and speed

OPTIONS:
    -o <output>      Output path ('-' for stdout). Input '-' reads stdin.
    -D <dict>        Shared-knowledge dictionary: any file both sides have
                     (e.g. typical samples of the data). The model reads it
                     before coding, so similar data costs far fewer bits.
                     Decompression needs the exact same file.
    -m <level>       Memory level 16..24 (default 22, ~140 MiB; 24 = ~480 MiB).
                     Higher = more memory, better compression on large inputs.
                     Decompression needs the same memory as compression.
    -b <MiB>         Block size for parallel compression (default 8). Inputs
                     larger than this are split into independent blocks that
                     compress and decompress on all cores. Smaller blocks =
                     more speed, slightly worse ratio. 0 = never split.
    -t <n>           Worker threads (default: all cores). Each thread holds
                     its own model, so memory grows with the thread count.
    -f               Overwrite the output if it exists.
    -h, --help       Show this help.
    -V, --version    Show the version.
";

struct Args {
    command: String,
    inputs: Vec<String>,
    output: Option<String>,
    mem_bits: u8,
    block_size: usize,
    threads: usize,
    dict: Option<String>,
    force: bool,
}

fn parse_args() -> Result<Option<Args>, String> {
    let mut it = std::env::args().skip(1);
    let mut command = None;
    let mut inputs = Vec::new();
    let mut output = None;
    let mut mem_bits = Options::default().mem_bits;
    let mut block_size = DEFAULT_BLOCK_SIZE;
    let mut threads = 0;
    let mut dict = None;
    let mut force = false;
    while let Some(a) = it.next() {
        match a.as_str() {
            "-h" | "--help" => return Ok(None),
            "-V" | "--version" => {
                println!("sedge {}", env!("CARGO_PKG_VERSION"));
                std::process::exit(0);
            }
            "-o" => output = Some(it.next().ok_or("-o needs a value")?),
            "-m" => {
                let v = it.next().ok_or("-m needs a value")?;
                mem_bits = v
                    .parse()
                    .ok()
                    .filter(|m| (MIN_MEM_BITS..=MAX_MEM_BITS).contains(m))
                    .ok_or(format!(
                        "-m must be between {MIN_MEM_BITS} and {MAX_MEM_BITS}"
                    ))?;
            }
            "-b" => {
                let v = it.next().ok_or("-b needs a value")?;
                let mib: usize = v.parse().map_err(|_| "-b must be a number of MiB")?;
                if mib > 4095 {
                    return Err("-b must be at most 4095 MiB".into());
                }
                block_size = mib << 20;
            }
            "-t" => {
                let v = it.next().ok_or("-t needs a value")?;
                threads = v.parse().map_err(|_| "-t must be a number")?;
            }
            "-D" => dict = Some(it.next().ok_or("-D needs a file")?),
            "-f" => force = true,
            _ if command.is_none() => command = Some(a),
            _ => inputs.push(a),
        }
    }
    let Some(command) = command else {
        return Ok(None);
    };
    Ok(Some(Args {
        command,
        inputs,
        output,
        mem_bits,
        block_size,
        threads,
        dict,
        force,
    }))
}

fn read_input(path: &str) -> io::Result<Vec<u8>> {
    if path == "-" {
        let mut buf = Vec::new();
        io::stdin().read_to_end(&mut buf)?;
        Ok(buf)
    } else {
        fs::read(path)
    }
}

fn write_output(path: &str, data: &[u8], force: bool) -> Result<(), String> {
    if path == "-" {
        return io::stdout()
            .write_all(data)
            .map_err(|e| format!("stdout: {e}"));
    }
    if !force && Path::new(path).exists() {
        return Err(format!("{path} already exists (use -f to overwrite)"));
    }
    fs::write(path, data).map_err(|e| format!("{path}: {e}"))
}

fn single_input(args: &Args) -> Result<&str, String> {
    match args.inputs.as_slice() {
        [one] => Ok(one),
        [] => Err("missing <input>".into()),
        _ => Err("expected exactly one <input>".into()),
    }
}

fn mib_per_s(bytes: usize, secs: f64) -> f64 {
    bytes as f64 / (1024.0 * 1024.0) / secs.max(1e-9)
}

fn run(args: Args) -> Result<(), String> {
    let opts = Options {
        mem_bits: args.mem_bits,
        block_size: args.block_size,
        threads: args.threads,
    };
    let dict = match &args.dict {
        Some(path) => fs::read(path).map_err(|e| format!("{path}: {e}"))?,
        None => Vec::new(),
    };
    match args.command.as_str() {
        "compress" | "c" => {
            let input = single_input(&args)?;
            let data = read_input(input).map_err(|e| format!("{input}: {e}"))?;
            let t = Instant::now();
            let packed = compress_with_dictionary(&data, &dict, &opts);
            let secs = t.elapsed().as_secs_f64();
            let out = args.output.clone().unwrap_or_else(|| {
                if input == "-" {
                    "-".into()
                } else {
                    format!("{input}.sedge")
                }
            });
            write_output(&out, &packed, args.force)?;
            if out != "-" {
                eprintln!(
                    "{input}: {} -> {} bytes ({:.2}%, {:.3} bits/byte) in {secs:.2}s [{:.2} MiB/s]",
                    data.len(),
                    packed.len(),
                    100.0 * packed.len() as f64 / data.len().max(1) as f64,
                    8.0 * packed.len() as f64 / data.len().max(1) as f64,
                    mib_per_s(data.len(), secs),
                );
            }
            Ok(())
        }
        "decompress" | "d" => {
            let input = single_input(&args)?;
            let packed = read_input(input).map_err(|e| format!("{input}: {e}"))?;
            let data = decompress_with_dictionary(&packed, &dict, args.threads)
                .map_err(|e| format!("{input}: {e}"))?;
            let out = args.output.clone().unwrap_or_else(|| {
                if input == "-" {
                    "-".into()
                } else if let Some(stem) = input.strip_suffix(".sedge") {
                    stem.into()
                } else {
                    format!("{input}.out")
                }
            });
            write_output(&out, &data, args.force)
        }
        "bench" | "b" => {
            if args.inputs.is_empty() {
                return Err("bench needs at least one file".into());
            }
            println!(
                "{:<28} {:>13} {:>13} {:>8} {:>8} {:>10} {:>10}",
                "file", "original", "compressed", "ratio", "bpb", "comp MB/s", "dec MB/s"
            );
            let (mut tot_in, mut tot_out) = (0usize, 0usize);
            for path in &args.inputs {
                let data = fs::read(path).map_err(|e| format!("{path}: {e}"))?;
                let t = Instant::now();
                let packed = compress_with_dictionary(&data, &dict, &opts);
                let tc = t.elapsed().as_secs_f64();
                let t = Instant::now();
                let back = decompress_with_dictionary(&packed, &dict, args.threads)
                    .map_err(|e| format!("{path}: {e}"))?;
                let td = t.elapsed().as_secs_f64();
                if back != data {
                    return Err(format!("{path}: ROUND-TRIP MISMATCH"));
                }
                tot_in += data.len();
                tot_out += packed.len();
                let name = Path::new(path)
                    .file_name()
                    .map(|n| n.to_string_lossy().into_owned())
                    .unwrap_or_else(|| path.clone());
                println!(
                    "{:<28} {:>13} {:>13} {:>7.2}% {:>8.3} {:>10.2} {:>10.2}",
                    name,
                    data.len(),
                    packed.len(),
                    100.0 * packed.len() as f64 / data.len().max(1) as f64,
                    8.0 * packed.len() as f64 / data.len().max(1) as f64,
                    mib_per_s(data.len(), tc),
                    mib_per_s(data.len(), td),
                );
            }
            if args.inputs.len() > 1 {
                println!(
                    "{:<28} {:>13} {:>13} {:>7.2}% {:>8.3}",
                    "TOTAL",
                    tot_in,
                    tot_out,
                    100.0 * tot_out as f64 / tot_in.max(1) as f64,
                    8.0 * tot_out as f64 / tot_in.max(1) as f64,
                );
            }
            println!("All files verified bit-for-bit.");
            Ok(())
        }
        other => Err(format!("unknown command '{other}' (try --help)")),
    }
}

fn main() -> ExitCode {
    match parse_args() {
        Ok(None) => {
            print!("{USAGE}");
            ExitCode::SUCCESS
        }
        Ok(Some(args)) => match run(args) {
            Ok(()) => ExitCode::SUCCESS,
            Err(e) => {
                eprintln!("sedge: {e}");
                ExitCode::FAILURE
            }
        },
        Err(e) => {
            eprintln!("sedge: {e}\n\n{USAGE}");
            ExitCode::from(2)
        }
    }
}
