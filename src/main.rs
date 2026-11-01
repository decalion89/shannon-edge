//! `sedge` — command-line front end for shannon-edge.

use shannon_edge::{
    compress, compress_with_dictionary, decompress_with_dictionary, decompress_with_threads, Error,
    Options, PrimedModel, DEFAULT_BLOCK_SIZE, MAX_MEM_BITS, MIN_MEM_BITS,
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
    sedge prime      <dict> [-o <model>] [-m <level>] [-f]
    sedge train      <sample>... -o <dict> [--budget <bytes>] [--lines] [-f]

    Wherever -D <dict> is accepted, -M <model> (a primed model) works too.

COMMANDS:
    compress, c      Compress <input> (default output: <input>.sedge)
    decompress, d    Decompress <input> (default output: <input> without .sedge)
    bench, b         Compress + decompress in memory, verify, report ratio and speed
    prime, p         Read <dict> once and save the primed model (default output:
                     <dict>.sedgem). Using it with -M skips re-reading the
                     dictionary; streams stay compatible with -D <dict>.
    train, t         Distil many samples into a dictionary of --budget bytes
                     (default 112640): keeps what recurs across samples,
                     most valuable content last. Each file is one sample, or
                     with --lines each line of each file is one.

OPTIONS:
    -o <output>      Output path ('-' for stdout). Input '-' reads stdin.
    -D <dict>        Shared-knowledge dictionary: any file both sides have
                     (e.g. typical samples of the data). The model reads it
                     before coding, so similar data costs far fewer bits.
                     Decompression needs the exact same file.
    -M <model>       A primed model from 'sedge prime': same effect as -D,
                     without the time to re-read the dictionary.
    -m <level>       Memory level 16..24 (default 22, ~140 MiB; 24 = ~480 MiB).
                     Higher = more memory, better compression on large inputs.
                     Decompression needs the same memory as compression.
    -b <MiB>         Block size for parallel compression (default 8). Inputs
                     larger than this are split into independent blocks that
                     compress and decompress on all cores. Smaller blocks =
                     more speed, slightly worse ratio. 0 = never split.
    -r <bytes>       Record length for data made of fixed-length records
                     (telemetry packets, table rows, scanlines): enables
                     column contexts. Default: detected automatically;
                     -r 0 disables it.
    -t <n>           Worker threads (default: all cores). Each thread holds
                     its own model, so memory grows with the thread count.
    --budget <bytes> Dictionary size for 'train'.
    --lines          'train': treat every line as a separate sample.
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
    model: Option<String>,
    budget: usize,
    lines: bool,
    record_len: Option<usize>,
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
    let mut model = None;
    let mut budget = shannon_edge::train::TrainOptions::default().budget;
    let mut lines = false;
    let mut record_len = None;
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
            "-M" => model = Some(it.next().ok_or("-M needs a file")?),
            "--budget" => {
                let v = it.next().ok_or("--budget needs a value")?;
                budget = v
                    .parse()
                    .map_err(|_| "--budget must be a number of bytes")?;
            }
            "--lines" => lines = true,
            "-r" => {
                let v = it.next().ok_or("-r needs a value")?;
                record_len = Some(v.parse().map_err(|_| "-r must be a number of bytes")?);
            }
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
        model,
        budget,
        lines,
        record_len,
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

enum Knowledge {
    None,
    Dict(Vec<u8>),
    Model(std::cell::RefCell<Box<PrimedModel>>),
}

fn run(args: Args) -> Result<(), String> {
    let opts = Options {
        mem_bits: args.mem_bits,
        block_size: args.block_size,
        threads: args.threads,
        record_len: args.record_len,
    };
    let knowledge = match (&args.dict, &args.model) {
        (Some(_), Some(_)) => return Err("use either -D or -M, not both".into()),
        (Some(path), None) => Knowledge::Dict(fs::read(path).map_err(|e| format!("{path}: {e}"))?),
        (None, Some(path)) => {
            let t = Instant::now();
            let raw = fs::read(path).map_err(|e| format!("{path}: {e}"))?;
            let m = PrimedModel::from_bytes(&raw).map_err(|e| format!("{path}: {e}"))?;
            eprintln!(
                "{path}: primed model loaded in {:.0} ms",
                t.elapsed().as_secs_f64() * 1e3
            );
            Knowledge::Model(std::cell::RefCell::new(Box::new(m)))
        }
        (None, None) => Knowledge::None,
    };
    let pack = |data: &[u8]| match &knowledge {
        Knowledge::None => compress(data, &opts),
        Knowledge::Dict(d) => compress_with_dictionary(data, d, &opts),
        // In place with a journal: cost proportional to the message.
        Knowledge::Model(m) => m.borrow_mut().compress_message(data, &opts),
    };
    let unpack = |packed: &[u8]| -> Result<Vec<u8>, Error> {
        match &knowledge {
            Knowledge::None => decompress_with_threads(packed, args.threads),
            Knowledge::Dict(d) => decompress_with_dictionary(packed, d, args.threads),
            Knowledge::Model(m) => m.borrow_mut().decompress_message(packed),
        }
    };
    match args.command.as_str() {
        "train" | "t" => {
            if args.inputs.is_empty() {
                return Err("train needs sample files".into());
            }
            let out = args.output.clone().ok_or("train needs -o <dict>")?;
            let mut owned = Vec::new();
            for path in &args.inputs {
                owned.push(fs::read(path).map_err(|e| format!("{path}: {e}"))?);
            }
            let samples: Vec<&[u8]> = if args.lines {
                owned
                    .iter()
                    .flat_map(|f| f.split(|&b| b == b'\n'))
                    .filter(|l| !l.is_empty())
                    .collect()
            } else {
                owned.iter().map(|f| &f[..]).collect()
            };
            let t = Instant::now();
            let topts = shannon_edge::train::TrainOptions {
                budget: args.budget,
                ..Default::default()
            };
            let dict = shannon_edge::train::train_dictionary(&samples, &topts);
            write_output(&out, &dict, args.force)?;
            eprintln!(
                "trained on {} samples ({} bytes) in {:.1}s -> {out} ({} bytes)",
                samples.len(),
                samples.iter().map(|s| s.len()).sum::<usize>(),
                t.elapsed().as_secs_f64(),
                dict.len()
            );
            Ok(())
        }
        "prime" | "p" => {
            let input = single_input(&args)?;
            if !matches!(knowledge, Knowledge::None) {
                return Err("prime takes the dictionary as its input, not -D/-M".into());
            }
            let dict = read_input(input).map_err(|e| format!("{input}: {e}"))?;
            if dict.is_empty() {
                return Err(format!("{input}: dictionary is empty"));
            }
            let t = Instant::now();
            let m = PrimedModel::new(&dict, &opts);
            let secs = t.elapsed().as_secs_f64();
            let bytes = m.to_bytes();
            let out = args
                .output
                .clone()
                .unwrap_or_else(|| format!("{input}.sedgem"));
            write_output(&out, &bytes, args.force)?;
            eprintln!(
                "{input}: primed in {secs:.2}s (memory level {}), model {} bytes -> {out}",
                m.mem_bits(),
                bytes.len()
            );
            Ok(())
        }
        "compress" | "c" => {
            let input = single_input(&args)?;
            let data = read_input(input).map_err(|e| format!("{input}: {e}"))?;
            let t = Instant::now();
            let packed = pack(&data);
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
            let data = unpack(&packed).map_err(|e| format!("{input}: {e}"))?;
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
                let packed = pack(&data);
                let tc = t.elapsed().as_secs_f64();
                let t = Instant::now();
                let back = unpack(&packed).map_err(|e| format!("{path}: {e}"))?;
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
