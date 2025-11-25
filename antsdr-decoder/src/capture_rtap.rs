use async_channel::Sender;
use pcap::{Capture, Device, Linktype};
use radiotap::Radiotap;
use ieee80211::{GenericFrame, mgmt_frame::ProbeRequestFrame};
use crate::types::{RtPkt, Source};

pub struct RadiotapPcap {
    dev: String
}

impl RadiotapPcap {
    pub fn new(dev: &str) -> anyhow::Result<Self> {Ok(Self { dev: dev.into() })}
}

#[async_trait::async_trait]
impl Source<RtPkt> for RadiotapPcap {
    async fn run(&mut self, tx: Sender<RtPkt>) -> anyhow::Result<()> {
        let mut cap = Capture::from_device(Device::from(self.dev.as_str()))?
            .immediate_mode(true)
            .promisc(true)
            .open()?;
        cap.set_datalink(Linktype(127))?; // 127 = DLT_IEEE802_11_RADIO

        loop {
            let packet = cap.next_packet()?;
            let header = Radiotap::from_bytes(packet.data)?;
            let rssi_dbm = if let Some(v) = header.antenna_signal {v.value} else {0};
                        
            // Extract the timestamp (or continue to next frame if it doesn't exist)
            let Some(ts) = header.tsft else {continue};
            let tsf = ts.value;

            // println!("RT: {}", tsf);

            let header_len = header.header.length as usize;
            let payload = &packet.data[header_len..];

            // Parse the 802.11 data
            let generic_frame = match GenericFrame::new(payload, false) {
                Ok(frame) => frame,
                Err(_) => {
                    println!("Failed to parse data to generic frame");
                    continue;
                },
            };

            // Check if we're dealing with a probe request
            // TODO: implement support for multiple frame types
            if !generic_frame.matches::<ProbeRequestFrame>() {
                continue;
            }

            // Attempt to parse the probe request to extract MAC address
            if let Some(Ok(probe_reqest_frame)) = generic_frame.parse_to_typed::<ProbeRequestFrame>() {
                let mac_address = probe_reqest_frame.header.transmitter_address.to_string();

                if mac_address != "11:22:33:44:55:66" {
                    // println!("Alien MAC: {:?} / {}", mac_address, tsf);
                    continue;
                } else {
                    tx.send(RtPkt { 
                        tsf: tsf, 
                        header: packet.data.to_vec(), 
                        mac: mac_address.to_string(), 
                        seq: probe_reqest_frame.header.sequence_control.sequence_number(),
                        rssi_dbm
                    }).await?;
                }
            }
        }
    }
}