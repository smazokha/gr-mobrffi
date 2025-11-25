use flexi_logger::{Cleanup, Criterion, Duplicate, Logger, Naming, FileSpec};

pub fn init() -> anyhow::Result<()> {
    Logger::try_with_str("info")?
        .log_to_file(FileSpec::default().directory("/var/log/ow-decoder"))
        .rotate(
            Criterion::Size(1_000_000), 
            Naming::Numbers,
            Cleanup::KeepLogFiles(3)
        )
        .duplicate_to_stdout(Duplicate::Info)
        .start()?;
    Ok(())
}