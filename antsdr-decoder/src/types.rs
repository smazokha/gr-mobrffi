use async_trait::async_trait;

#[derive(Debug, Clone)]
pub struct IqPkt {
    pub tsf:   u64,
    pub bytes: Vec<u8>,
}

#[derive(Debug, Clone)]
pub struct RtPkt {
    pub tsf: u64,
    pub header: Vec<u8>,
    pub mac: String,
    pub seq: u16,
    pub rssi_dbm: i8
}

pub trait Timestamped { fn tsf(&self) -> u64; }
impl Timestamped for IqPkt { fn tsf(&self) -> u64 { self.tsf } }
impl Timestamped for RtPkt { fn tsf(&self) -> u64 { self.tsf } }

#[async_trait]
pub trait Source<P: Timestamped + Send + 'static>: Send + Sync {
    async fn run(&mut self, tx: async_channel::Sender<P>) -> anyhow::Result<()>;
}

#[async_trait]
pub trait Sink: Send + Sync {
    async fn consume(&self, rt: RtPkt, iq: IqPkt) -> anyhow::Result<()>;
}