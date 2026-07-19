use chrono::Local;
use serde::Serialize;
use signal_hook::consts::{SIGHUP, SIGINT, SIGTERM};
use std::collections::HashSet;
use std::env;
use std::error::Error;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use sysinfo::{ProcessesToUpdate, System};

type DynError = Box<dyn Error + Send + Sync>;

#[derive(Clone, Debug)]
struct Config {
    log_root: PathBuf,
    node_threshold: f32,
    windowserver_enabled: bool,
    windowserver_threshold: f32,
    interval: Duration,
    sample_duration_sec: u64,
    sample_interval_ms: u64,
    cooldown: Duration,
    verbose: bool,
    max_events: usize,
    max_log_bytes: u64,
    max_capture_workers: usize,
}

impl Config {
    fn from_env() -> Result<Self, DynError> {
        let home = env::var_os("HOME")
            .map(PathBuf::from)
            .ok_or("HOME is not set")?;
        let log_root = env::var_os("WATCH_LOG_ROOT")
            .map(PathBuf::from)
            .unwrap_or_else(|| home.join(".hermes/logs/node-hot-watch"));

        Ok(Self {
            log_root,
            node_threshold: env_value("WATCH_CPU_THRESHOLD", 80.0_f32)?,
            windowserver_enabled: env_bool("WATCH_WINDOWSERVER_ENABLED", true),
            windowserver_threshold: env_value("WATCH_WINDOWSERVER_THRESHOLD", 50.0_f32)?,
            interval: Duration::from_secs(env_value("WATCH_INTERVAL_SEC", 2_u64)?.max(1)),
            sample_duration_sec: env_value("WATCH_SAMPLE_DURATION_SEC", 5_u64)?.max(1),
            sample_interval_ms: env_value("WATCH_SAMPLE_INTERVAL_MS", 10_u64)?.max(1),
            cooldown: Duration::from_secs(env_value("WATCH_COOLDOWN_SEC", 120_u64)?),
            verbose: env_bool("WATCH_VERBOSE", false),
            max_events: env_value("WATCH_MAX_EVENTS", 200_usize)?.max(1),
            max_log_bytes: env_value("WATCH_MAX_LOG_MB", 200_u64)?
                .max(1)
                .saturating_mul(1024 * 1024),
            max_capture_workers: env_value("WATCH_MAX_CAPTURE_WORKERS", 2_usize)?.clamp(1, 8),
        })
    }
}

fn env_value<T>(name: &str, default: T) -> Result<T, DynError>
where
    T: std::str::FromStr,
    T::Err: Error + Send + Sync + 'static,
{
    match env::var(name) {
        Ok(value) => Ok(value.parse::<T>()?),
        Err(env::VarError::NotPresent) => Ok(default),
        Err(error) => Err(Box::new(error)),
    }
}

fn env_bool(name: &str, default: bool) -> bool {
    match env::var(name) {
        Ok(value) => matches!(value.as_str(), "1" | "true" | "TRUE" | "yes" | "YES"),
        Err(_) => default,
    }
}

#[derive(Clone, Copy, Debug, Serialize)]
enum CaptureKind {
    #[serde(rename = "node-or-codex")]
    NodeOrCodex,
    #[serde(rename = "windowserver")]
    WindowServer,
}

impl CaptureKind {
    fn key(self) -> &'static str {
        match self {
            Self::NodeOrCodex => "node",
            Self::WindowServer => "windowserver",
        }
    }

    fn summary_name(self) -> &'static str {
        match self {
            Self::NodeOrCodex => "node-or-codex",
            Self::WindowServer => "windowserver",
        }
    }
}

#[derive(Clone, Debug)]
struct Trigger {
    pid: u32,
    process_name: String,
    process_start_time: u64,
    kind: CaptureKind,
    cpu: f32,
    threshold: f32,
    cpu_source: &'static str,
}

impl Trigger {
    fn key(&self) -> String {
        format!(
            "{}-{}-{}",
            self.kind.key(),
            self.pid,
            self.process_start_time
        )
    }
}

#[derive(Serialize)]
struct EventMetadata<'a> {
    timestamp: &'a str,
    pid: u32,
    process_name: &'a str,
    process_start_time: u64,
    kind: CaptureKind,
    trigger_cpu: f32,
    threshold: f32,
    cpu_source: &'a str,
    sample_duration_sec: u64,
    sample_interval_ms: u64,
    sample_ok: bool,
}

struct PidGuard {
    path: PathBuf,
    pid: u32,
}

impl PidGuard {
    fn acquire(path: PathBuf) -> Result<Self, DynError> {
        if let Ok(existing) = fs::read_to_string(&path) {
            if let Ok(pid) = existing.trim().parse::<u32>() {
                if pid_is_alive(pid) {
                    return Err(format!("watcher already running with PID {pid}").into());
                }
            }
            let _ = fs::remove_file(&path);
        }

        let pid = std::process::id();
        OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(&path)?
            .write_all(pid.to_string().as_bytes())?;
        Ok(Self { path, pid })
    }
}

impl Drop for PidGuard {
    fn drop(&mut self) {
        if fs::read_to_string(&self.path)
            .ok()
            .map(|value| value.trim() == self.pid.to_string())
            .unwrap_or(false)
        {
            let _ = fs::remove_file(&self.path);
        }
    }
}

fn pid_is_alive(pid: u32) -> bool {
    let result = unsafe { libc::kill(pid as libc::pid_t, 0) };
    result == 0 || std::io::Error::last_os_error().raw_os_error() == Some(libc::EPERM)
}

fn now_epoch_secs() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

fn log_line(message: impl AsRef<str>) {
    println!(
        "[{}] {}",
        Local::now().format("%Y-%m-%d %H:%M:%S"),
        message.as_ref()
    );
}

fn verbose(config: &Config, message: impl AsRef<str>) {
    if config.verbose {
        log_line(message);
    }
}

fn cooldown_ready(config: &Config, trigger: &Trigger) -> Result<bool, DynError> {
    let cooldown_dir = config.log_root.join(".cooldowns");
    fs::create_dir_all(&cooldown_dir)?;
    let path = cooldown_dir.join(format!("{}.last", trigger.key()));
    let now = now_epoch_secs();

    if let Ok(value) = fs::read_to_string(&path) {
        if let Ok(last) = value.trim().parse::<u64>() {
            if now.saturating_sub(last) < config.cooldown.as_secs() {
                return Ok(false);
            }
        }
    }

    fs::write(path, now.to_string())?;
    Ok(true)
}

fn reserve_worker(active: &AtomicUsize, maximum: usize) -> bool {
    active
        .fetch_update(Ordering::SeqCst, Ordering::SeqCst, |current| {
            (current < maximum).then_some(current + 1)
        })
        .is_ok()
}

fn collect_triggers(system: &System, config: &Config) -> Vec<Trigger> {
    let mut node_candidates = Vec::new();
    let mut windowserver_process = None;

    for (pid, process) in system.processes() {
        let name = process.name().to_string_lossy().into_owned();
        let cpu = process.cpu_usage();
        let pid = pid.as_u32();

        if (name == "node" || name == "codex") && cpu >= config.node_threshold {
            node_candidates.push(Trigger {
                pid,
                process_name: name.clone(),
                process_start_time: process.start_time(),
                kind: CaptureKind::NodeOrCodex,
                cpu,
                threshold: config.node_threshold,
                cpu_source: "interval",
            });
        }

        if config.windowserver_enabled && name == "WindowServer" {
            windowserver_process = Some((pid, name, process.start_time()));
        }
    }

    node_candidates.sort_by(|left, right| {
        right
            .cpu
            .partial_cmp(&left.cpu)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    node_candidates.truncate(1);
    if let Some((pid, process_name, process_start_time)) = windowserver_process {
        if let Some(cpu) = ps_cpu_usage(pid) {
            if cpu >= config.windowserver_threshold {
                node_candidates.push(Trigger {
                    pid,
                    process_name,
                    process_start_time,
                    kind: CaptureKind::WindowServer,
                    cpu,
                    threshold: config.windowserver_threshold,
                    cpu_source: "ps-decay-average",
                });
            }
        }
    }
    node_candidates
}

fn ps_cpu_usage(pid: u32) -> Option<f32> {
    let pid = pid.to_string();
    let output = Command::new("/bin/ps")
        .args(["-p", &pid, "-o", "%cpu="])
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }
    String::from_utf8_lossy(&output.stdout)
        .trim()
        .parse::<f32>()
        .ok()
}

fn schedule_capture(
    config: Arc<Config>,
    trigger: Trigger,
    active_workers: Arc<AtomicUsize>,
    in_flight: Arc<Mutex<HashSet<String>>>,
    retention_lock: Arc<Mutex<()>>,
) {
    let key = trigger.key();
    if in_flight
        .lock()
        .expect("in-flight lock poisoned")
        .contains(&key)
    {
        return;
    }
    if !reserve_worker(&active_workers, config.max_capture_workers) {
        verbose(&config, "Capture worker limit reached; deferring trigger");
        return;
    }
    match cooldown_ready(&config, &trigger) {
        Ok(true) => {}
        Ok(false) => {
            active_workers.fetch_sub(1, Ordering::SeqCst);
            return;
        }
        Err(error) => {
            active_workers.fetch_sub(1, Ordering::SeqCst);
            log_line(format!(
                "Could not update cooldown for PID {}: {error}",
                trigger.pid
            ));
            return;
        }
    }
    in_flight
        .lock()
        .expect("in-flight lock poisoned")
        .insert(key.clone());

    thread::spawn(move || {
        let capture_result = std::panic::catch_unwind(|| capture_event(&config, &trigger));
        match capture_result {
            Ok(Ok(event_dir)) => {
                log_line(format!(
                    "Captured hot {} process PID {} into {}",
                    trigger.kind.summary_name(),
                    trigger.pid,
                    event_dir.display()
                ));
            }
            Ok(Err(error)) => log_line(format!(
                "Capture failed for {} PID {}: {error}",
                trigger.kind.summary_name(),
                trigger.pid
            )),
            Err(_) => log_line(format!(
                "Capture panicked for {} PID {}",
                trigger.kind.summary_name(),
                trigger.pid
            )),
        }

        in_flight
            .lock()
            .expect("in-flight lock poisoned")
            .remove(&key);
        let remaining_workers = active_workers.fetch_sub(1, Ordering::SeqCst) - 1;
        if remaining_workers == 0 {
            if let Ok(_guard) = retention_lock.lock() {
                if let Err(error) = enforce_retention(&config) {
                    log_line(format!("Log retention failed: {error}"));
                }
            }
        }
    });
}

fn run_command(program: &str, args: &[&str], stdout: &Path, stderr: &Path) -> bool {
    let stdout_file = match File::create(stdout) {
        Ok(file) => file,
        Err(_) => return false,
    };
    let stderr_file = match File::create(stderr) {
        Ok(file) => file,
        Err(_) => return false,
    };
    Command::new(program)
        .args(args)
        .stdout(Stdio::from(stdout_file))
        .stderr(Stdio::from(stderr_file))
        .status()
        .map(|status| status.success())
        .unwrap_or(false)
}

fn command_output(program: &str, args: &[&str]) -> Vec<u8> {
    Command::new(program)
        .args(args)
        .output()
        .map(|output| {
            let mut bytes = output.stdout;
            bytes.extend_from_slice(&output.stderr);
            bytes
        })
        .unwrap_or_default()
}

fn write_parent_chain(pid: u32, output: &Path) -> Result<(), DynError> {
    let mut file = File::create(output)?;
    let mut current = pid;
    let mut seen = HashSet::new();

    while current > 0 && seen.insert(current) && seen.len() <= 32 {
        let current_string = current.to_string();
        file.write_all(&command_output(
            "/bin/ps",
            &[
                "-ww",
                "-p",
                &current_string,
                "-o",
                "pid=,ppid=,pgid=,etime=,state=,%cpu=,%mem=,comm=,args=",
            ],
        ))?;
        let parent = command_output("/bin/ps", &["-p", &current_string, "-o", "ppid="]);
        current = String::from_utf8_lossy(&parent)
            .trim()
            .parse::<u32>()
            .unwrap_or(0);
    }
    Ok(())
}

fn capture_event(config: &Config, trigger: &Trigger) -> Result<PathBuf, DynError> {
    fs::create_dir_all(&config.log_root)?;
    let now = Local::now();
    let stamp = now.format("%Y%m%d-%H%M%S");
    let event_dir = config
        .log_root
        .join(format!("event-{stamp}-pid-{}", trigger.pid));
    fs::create_dir_all(&event_dir)?;

    let timestamp = now.format("%Y-%m-%d %H:%M:%S %z").to_string();
    let summary_path = event_dir.join("summary.txt");
    let mut summary = File::create(&summary_path)?;
    writeln!(summary, "timestamp: {timestamp}")?;
    writeln!(summary, "pid: {}", trigger.pid)?;
    writeln!(summary, "kind: {}", trigger.kind.summary_name())?;
    writeln!(summary, "trigger_cpu: {:.1}", trigger.cpu)?;
    writeln!(summary, "threshold: {:.1}", trigger.threshold)?;
    writeln!(summary, "cpu_source: {}", trigger.cpu_source)?;
    writeln!(
        summary,
        "sample_duration_sec: {}",
        config.sample_duration_sec
    )?;
    writeln!(summary, "sample_interval_ms: {}", config.sample_interval_ms)?;
    writeln!(summary)?;
    drop(summary);

    let pid = trigger.pid.to_string();
    run_command(
        "/bin/ps",
        &[
            "-ww",
            "-p",
            &pid,
            "-o",
            "pid,ppid,pgid,etime,state,%cpu,%mem,user,comm,args",
        ],
        &event_dir.join("ps.txt"),
        &event_dir.join("ps.stderr.txt"),
    );
    run_command(
        "/bin/ps",
        &["-ww", "-p", &pid, "-o", "lstart="],
        &event_dir.join("start-time.txt"),
        &event_dir.join("start-time.stderr.txt"),
    );

    let parent_output = command_output("/bin/ps", &["-p", &pid, "-o", "ppid="]);
    let parent_pid = String::from_utf8_lossy(&parent_output).trim().to_string();
    let mut target_parent = File::create(event_dir.join("target-and-parent.txt"))?;
    writeln!(target_parent, "target")?;
    target_parent.write_all(&command_output(
        "/bin/ps",
        &[
            "-ww",
            "-p",
            &pid,
            "-o",
            "pid,ppid,pgid,etime,state,%cpu,%mem,user,comm,args",
        ],
    ))?;
    if !parent_pid.is_empty() {
        writeln!(target_parent, "\nparent")?;
        target_parent.write_all(&command_output(
            "/bin/ps",
            &[
                "-ww",
                "-p",
                &parent_pid,
                "-o",
                "pid,ppid,pgid,etime,state,%cpu,%mem,user,comm,args",
            ],
        ))?;
    }
    write_parent_chain(trigger.pid, &event_dir.join("parent-chain.txt"))?;

    run_command(
        "/usr/sbin/lsof",
        &["-a", "-p", &pid, "-d", "cwd", "-Fn"],
        &event_dir.join("cwd.txt"),
        &event_dir.join("cwd.stderr.txt"),
    );
    if let Ok(mut cwd_file) = File::open(event_dir.join("cwd.txt")) {
        let mut cwd_contents = String::new();
        cwd_file.read_to_string(&mut cwd_contents)?;
        if let Some(cwd) = cwd_contents.lines().find_map(|line| line.strip_prefix('n')) {
            let mut summary = OpenOptions::new().append(true).open(&summary_path)?;
            writeln!(summary, "cwd: {cwd}")?;
        }
    }
    run_command(
        "/usr/sbin/lsof",
        &["-a", "-p", &pid, "-n", "-P"],
        &event_dir.join("open-files.txt"),
        &event_dir.join("open-files.stderr.txt"),
    );
    run_command(
        "/usr/sbin/lsof",
        &["-a", "-p", &pid, "-i", "-n", "-P"],
        &event_dir.join("network.txt"),
        &event_dir.join("network.stderr.txt"),
    );

    run_command(
        "/bin/sh",
        &["-c", "/bin/ps -ww -axo pid,ppid,%cpu,%mem,rss,etime,state,comm,args | /usr/bin/sort -k3,3nr | /usr/bin/head -n 50"],
        &event_dir.join("system-processes.txt"),
        &event_dir.join("system-processes.stderr.txt"),
    );
    run_command(
        "/bin/sh",
        &[
            "-c",
            "/usr/bin/top -l 2 -n 0 -s 1 | /usr/bin/awk '/Load Avg:|CPU usage:|PhysMem:/'",
        ],
        &event_dir.join("system-summary.txt"),
        &event_dir.join("system-summary.stderr.txt"),
    );
    run_command(
        "/usr/bin/pmset",
        &["-g", "therm"],
        &event_dir.join("thermal.txt"),
        &event_dir.join("thermal.stderr.txt"),
    );

    if matches!(trigger.kind, CaptureKind::WindowServer) {
        let front_asn = command_output("/usr/bin/lsappinfo", &["front"]);
        let front_asn_string = String::from_utf8_lossy(&front_asn).trim().to_string();
        let mut frontmost = File::create(event_dir.join("frontmost-app.txt"))?;
        frontmost.write_all(&front_asn)?;
        if !front_asn_string.is_empty() {
            frontmost.write_all(&command_output(
                "/usr/bin/lsappinfo",
                &["info", "-only", "name,pid,bundleID", &front_asn_string],
            ))?;
        }
        run_command(
            "/usr/bin/lsappinfo",
            &["list"],
            &event_dir.join("applications.txt"),
            &event_dir.join("applications.stderr.txt"),
        );
        run_command(
            "/usr/sbin/system_profiler",
            &["SPDisplaysDataType", "-detailLevel", "mini"],
            &event_dir.join("displays.txt"),
            &event_dir.join("displays.stderr.txt"),
        );
    }

    let sample_duration = config.sample_duration_sec.to_string();
    let sample_interval = config.sample_interval_ms.to_string();
    let sample_path = event_dir.join("sample.txt");
    let sample_path_string = sample_path.to_string_lossy().to_string();
    let sample_ok = run_command(
        "/usr/bin/sample",
        &[
            &pid,
            &sample_duration,
            &sample_interval,
            "-mayDie",
            "-file",
            &sample_path_string,
        ],
        &event_dir.join("sample.stdout.txt"),
        &event_dir.join("sample.stderr.txt"),
    );
    let mut summary = OpenOptions::new().append(true).open(&summary_path)?;
    writeln!(
        summary,
        "sample: {}",
        if sample_ok { "ok" } else { "failed" }
    )?;

    let metadata = EventMetadata {
        timestamp: &timestamp,
        pid: trigger.pid,
        process_name: &trigger.process_name,
        process_start_time: trigger.process_start_time,
        kind: trigger.kind,
        trigger_cpu: trigger.cpu,
        threshold: trigger.threshold,
        cpu_source: trigger.cpu_source,
        sample_duration_sec: config.sample_duration_sec,
        sample_interval_ms: config.sample_interval_ms,
        sample_ok,
    };
    serde_json::to_writer_pretty(File::create(event_dir.join("event.json"))?, &metadata)?;
    Ok(event_dir)
}

fn directory_size(path: &Path) -> u64 {
    let mut total = 0_u64;
    let Ok(entries) = fs::read_dir(path) else {
        return 0;
    };
    for entry in entries.flatten() {
        let entry_path = entry.path();
        if let Ok(metadata) = entry.metadata() {
            if metadata.is_dir() {
                total = total.saturating_add(directory_size(&entry_path));
            } else {
                total = total.saturating_add(metadata.len());
            }
        }
    }
    total
}

fn enforce_retention(config: &Config) -> Result<(), DynError> {
    let mut events = fs::read_dir(&config.log_root)?
        .filter_map(Result::ok)
        .filter(|entry| {
            entry.file_type().map(|kind| kind.is_dir()).unwrap_or(false)
                && entry.file_name().to_string_lossy().starts_with("event-")
        })
        .map(|entry| {
            let path = entry.path();
            let size = directory_size(&path);
            (path, size)
        })
        .collect::<Vec<_>>();
    events.sort_by(|left, right| left.0.file_name().cmp(&right.0.file_name()));
    let mut total = events.iter().map(|(_, size)| *size).sum::<u64>();

    while events.len() > config.max_events || total > config.max_log_bytes {
        let (path, size) = events.remove(0);
        fs::remove_dir_all(&path)?;
        total = total.saturating_sub(size);
        log_line(format!("Pruned old event {}", path.display()));
    }
    Ok(())
}

fn sleep_interruptibly(duration: Duration, stop_requested: &AtomicBool) {
    let quantum = Duration::from_millis(100);
    let mut remaining = duration;
    while !stop_requested.load(Ordering::Relaxed) && remaining > Duration::ZERO {
        let step = remaining.min(quantum);
        thread::sleep(step);
        remaining = remaining.saturating_sub(step);
    }
}

fn run_watcher(config: Config, once: bool) -> Result<(), DynError> {
    fs::create_dir_all(config.log_root.join(".cooldowns"))?;
    let stop_requested = Arc::new(AtomicBool::new(false));
    for signal in [SIGTERM, SIGINT, SIGHUP] {
        signal_hook::flag::register(signal, Arc::clone(&stop_requested))?;
    }

    let _pid_guard = if once {
        None
    } else {
        Some(PidGuard::acquire(config.log_root.join("watcher.pid"))?)
    };
    let config = Arc::new(config);
    let active_workers = Arc::new(AtomicUsize::new(0));
    let in_flight = Arc::new(Mutex::new(HashSet::new()));
    let retention_lock = Arc::new(Mutex::new(()));
    let mut system = System::new();
    system.refresh_processes(ProcessesToUpdate::All, true);

    verbose(
        &config,
        format!(
            "Rust watcher active: node/codex >= {:.1}%, WindowServer >= {:.1}%, interval {:?}",
            config.node_threshold, config.windowserver_threshold, config.interval
        ),
    );

    loop {
        sleep_interruptibly(config.interval, &stop_requested);
        if stop_requested.load(Ordering::Relaxed) {
            break;
        }
        system.refresh_processes(ProcessesToUpdate::All, true);
        let triggers = collect_triggers(&system, &config);
        if triggers.is_empty() {
            verbose(&config, "No monitored process is above its threshold");
        }
        for trigger in triggers {
            schedule_capture(
                Arc::clone(&config),
                trigger,
                Arc::clone(&active_workers),
                Arc::clone(&in_flight),
                Arc::clone(&retention_lock),
            );
        }
        if once {
            break;
        }
    }

    while active_workers.load(Ordering::SeqCst) > 0 {
        thread::sleep(Duration::from_millis(100));
    }
    Ok(())
}

fn print_help() {
    println!(
        "watch-hot-process {}\n\nUsage: watch-hot-process [--once] [--version] [--help]",
        env!("CARGO_PKG_VERSION")
    );
}

fn main() -> Result<(), DynError> {
    let mut once = false;
    for argument in env::args().skip(1) {
        match argument.as_str() {
            "--once" => once = true,
            "--version" => {
                println!("watch-hot-process {}", env!("CARGO_PKG_VERSION"));
                return Ok(());
            }
            "--help" | "-h" => {
                print_help();
                return Ok(());
            }
            _ => return Err(format!("unknown option: {argument}").into()),
        }
    }

    if !cfg!(target_os = "macos") {
        return Err("watch-hot-process only supports macOS".into());
    }
    run_watcher(Config::from_env()?, once)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn worker_reservation_is_bounded() {
        let active = AtomicUsize::new(0);
        assert!(reserve_worker(&active, 2));
        assert!(reserve_worker(&active, 2));
        assert!(!reserve_worker(&active, 2));
    }

    #[test]
    fn event_kind_names_remain_compatible() {
        assert_eq!(CaptureKind::NodeOrCodex.summary_name(), "node-or-codex");
        assert_eq!(CaptureKind::WindowServer.summary_name(), "windowserver");
    }
}
