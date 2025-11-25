use async_trait::async_trait;
use byteorder::{ByteOrder, LittleEndian, WriteBytesExt};
use tokio::{net::UdpSocket};

use crate::types::{IqPkt, RtPkt, Sink};

const START_IDX: usize = 400;
const VEC_LEN: usize = 320; // number of complex samples to send

pub struct NetSink {
    socket: UdpSocket,
    stream_raw: bool,
}

impl NetSink {
    pub async fn new(target: &str, stream_raw: bool) -> anyhow::Result<Self> {
        let socket = UdpSocket::bind("0.0.0.0:0").await?;
        socket.connect(target).await?;
        Ok(Self { socket, stream_raw })
    }
}

#[async_trait]
impl Sink for NetSink {
    async fn consume(&self, rt: RtPkt, iq: IqPkt) -> anyhow::Result<()> {
        let delta = rt.tsf - iq.tsf;

        // Layout: [TSF u16 x4] + [I u16, Q u16, aux0 u16, aux1 u16] * M_total
        let raw = &iq.bytes;
        if raw.len() < 8 { return Ok(()); } // must at least hold TSF

        // Sending only IQ samples
        if self.stream_raw {
            let body = &raw[8..]; // past TSF
            let sym_stride = 8; // 4 x u16 = 8 bytes per symbol
            let start = START_IDX;
            let stop  = START_IDX + VEC_LEN;

            let mut out = Vec::<u8>::with_capacity(VEC_LEN * 2 * 4); // 320*(I,Q)*f32

            // Accumulators for optional energy stats
            let mut sum_sq: f32 = 0.0;
            let mut max_mag2: f32 = 0.0;
            let mut n_sent: usize = 0;

            for k in start..stop {
                let off = k * sym_stride;
                if off + sym_stride > body.len() {
                    break; // not enough data to fill the window
                }

                // Read I, Q as u16 (LE), reinterpret as i16
                let i_u16 = LittleEndian::read_u16(&body[off..off + 2]);
                let q_u16 = LittleEndian::read_u16(&body[off + 2..off + 4]);
                let i_s = i16::from_le_bytes((i_u16 as u16).to_le_bytes());
                let q_s = i16::from_le_bytes((q_u16 as u16).to_le_bytes());

                // Normalize to [-1, 1)
                let i_f = (i_s as f32) / 32768.0;
                let q_f = (q_s as f32) / 32768.0;

                // Accumulate stats
                let mag2 = i_f * i_f + q_f * q_f;
                sum_sq += mag2;
                if mag2 > max_mag2 {
                    max_mag2 = mag2;
                }

                // Pack as interleaved f32 IQ (little-endian)
                out.write_f32::<LittleEndian>(i_f)?;
                out.write_f32::<LittleEndian>(q_f)?;
                n_sent += 1;
            }

            print_energy_stats(rt, iq, delta, sum_sq, max_mag2);

            // Send headerless c32 frame
            self.socket.send(&out).await?;

        } else { // Sending IQ samples + RadioTap
            let mut out = Vec::with_capacity(16 + 2 + 2 + rt.header.len() + iq.bytes.len());
            out.write_u64::<LittleEndian>(rt.tsf)?;
            out.write_u64::<LittleEndian>(iq.tsf)?;
            out.write_u16::<LittleEndian>(rt.header.len() as u16)?;
            out.write_u16::<LittleEndian>(iq.bytes.len() as u16)?;
            out.extend_from_slice(&rt.header);
            out.extend_from_slice(&iq.bytes);

            self.socket.send(&out).await?;   

            print_general_stats(rt, iq, delta);     
        }

        Ok(())
    }
}

fn print_energy_stats(rt: RtPkt, iq: IqPkt, delta: u64, sum_sq: f32, max_mag2: f32) {
    let energy = sum_sq;
    let rms = (sum_sq / (VEC_LEN as f32)).sqrt();
    let peak = max_mag2.sqrt();

    println!(
        "[{}]: TSF_iq={} (dt:{}), SEQ={}, RSSI_dBm={} | frame[{}:{}) -> energy={:.6}, rms={:.6}, peak={:.6}",
        rt.mac,
        iq.tsf,
        delta,
        rt.seq,
        rt.rssi_dbm,
        START_IDX,
        START_IDX + VEC_LEN,
        energy,
        rms,
        peak
    );
}

fn print_general_stats(rt: RtPkt, iq: IqPkt, delta: u64) {
    println!(
        "[{}]: TSF: {} (dt: {}), SEQ: {}, RSSI (dBm): {}",
        rt.mac, iq.tsf, delta, rt.seq, rt.rssi_dbm
    );
}