use crate::types::{IqPkt, RtPkt, Sink, Timestamped};
use async_channel::Receiver;
use std::{collections::HashMap, sync::Arc};

const STALE_WINDOW_US: u64 = 1_000; // How long (µs) we keep an unmatched packet before discarding it.

pub struct Matcher<S: Sink + 'static> {
    rt_rx: Receiver<RtPkt>,
    iq_rx: Receiver<IqPkt>,
    sink:  Arc<S>,
}

impl<S: Sink + 'static> Matcher<S> {
    pub fn new(rt_rx: Receiver<RtPkt>,
               iq_rx: Receiver<IqPkt>,
               sink:  Arc<S>) -> Self
    {
        Self { rt_rx, iq_rx, sink }
    }

    pub async fn run(mut self) -> anyhow::Result<()> {
        use tokio::select;

        // Unmatched packets waiting for their counterpart.
        let mut rt_waiting: HashMap<u64, RtPkt> = HashMap::new();
        let mut iq_waiting: HashMap<u64, IqPkt> = HashMap::new();

        // Track the newest TSF we've seen to implement aging.
        let mut newest_tsf: u64 = 0;

        loop {
            select! {
                // Radiotap frame
                Ok(rt) = self.rt_rx.recv() => {
                    let tsf = rt.tsf();
                    newest_tsf = newest_tsf.max(tsf);

                    match iq_waiting.remove(&tsf) {
                        Some(iq) => self.sink.consume(rt, iq).await?,
                        None     => { rt_waiting.insert(tsf, rt); }
                    }
                }

                // IQ frame
                Ok(iq) = self.iq_rx.recv() => {
                    let tsf = iq.tsf();
                    newest_tsf = newest_tsf.max(tsf);

                    match rt_waiting.remove(&tsf) {
                        Some(rt) => self.sink.consume(rt, iq).await?,
                        None     => { iq_waiting.insert(tsf, iq); }
                    }
                }

                else => break,
            }

            let cutoff = newest_tsf.saturating_sub(STALE_WINDOW_US);
            rt_waiting.retain(|&tsf, _| tsf >= cutoff);
            iq_waiting.retain(|&tsf, _| tsf >= cutoff);
        }

        Ok(())
    }
}