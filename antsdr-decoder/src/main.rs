mod logging;
mod types;
mod capture_rtap;
mod capture_iq;
mod matcher;
mod sink_net;

use std::sync::Arc;
use clap::{Parser, ValueEnum};

use types::{IqPkt, RtPkt, Source};
use capture_rtap::RadiotapPcap;
use capture_iq::IqUdp;
use tokio::process::Command;
use sink_net::NetSink;
use matcher::Matcher;

#[derive(Copy, Clone, Debug, ValueEnum)]
enum Mode {
    Raw, // send ONLY raw IQ samples (320-long preamble)
    Full, // send FULL buffer + radiotap header for full capture
}

#[derive(Parser, Debug)]
#[command(name = "ow-decoder", about = "MobRFFI WiFi traffic capture tool.")]
struct Args {
    /// Mode for streaming data: RAW (send only 320-long preamble IQ samples) or FULL (send full binary buffer and radiotap header)
    #[arg(long, default_value_t = Mode::Raw, value_enum)]
    mode: Mode,
}

#[tokio::main]
async fn main() -> anyhow::Result<()>{
    logging::init()?;

    let args = Args::parse();
    let stream_raw = matches!(args.mode, Mode::Raw);

    println!("Streaming mode: {:?}", args.mode);

    // NOTE: for this command to work, we need to use a custom-compiled version
    //       of the side_ch_cth, which has 127.0.0.1 (localhost) server IP specified.
    // To compile this code on Ubuntu for the AntSDR, do the following:
    // 0 [on AntSDR]: cd /root/openwifi && mv side_ch_ctl side_ch_ctl_original
    // 1 [host]. Go to openwifi/user_space/side_ch_ctl_src
    // 2 [host]. Install: sudo apt-get install gcc-arm-linux-gnueabihf
    // 3 [host]. Compile: arm-linux-gnueabihf-gcc -O2 -static -s -o side_ch_ctl side_ch_ctl.c
    // 4 [host]. Send to AntSDR: scp side_ch_ctl root@192.168.10.122:/root/openwifi
    Command::new("/root/openwifi/side_ch_ctl").arg("g1") // replace g by g10 for sending data every 10 ms (default 100 ms)
        .stdout(std::process::Stdio::null()) // silences the command output
        .spawn()?;

    let (rt_tx, rt_rx) = async_channel::bounded::<RtPkt>(64);
    let (iq_tx, iq_rx) = async_channel::bounded::<IqPkt>(64);

    let sink = Arc::new(NetSink::new("192.168.10.1:9000", stream_raw).await?);
    let matcher = Matcher::new(rt_rx, iq_rx, sink);

    tokio::try_join!(
        tokio::spawn(async move { RadiotapPcap::new("sdr0")?.run(rt_tx).await }),
        tokio::spawn(async move { IqUdp::new(4000)?.run(iq_tx).await }),
        tokio::spawn(async move { matcher.run().await })
    )?;

    Ok(())
}