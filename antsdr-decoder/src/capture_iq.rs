use std::net::UdpSocket;
use async_channel::Sender;
use anyhow::Context;
use byteorder::{ByteOrder, LittleEndian};   
use crate::types::{IqPkt, Source};

pub struct IqUdp { socket: UdpSocket }

impl IqUdp {
    pub fn new(port: u16) -> anyhow::Result<Self> {
        Ok(Self { socket: UdpSocket::bind(("0.0.0.0", port))? })
    }
}

#[async_trait::async_trait]
impl Source<IqPkt> for IqUdp {
    async fn run(&mut self, tx: Sender<IqPkt>) -> anyhow::Result<()> {
        println!("Started!");

        let mut buf = vec![0u8; 65_600];

        loop {
            // Receive the payload
            let len = self.socket.recv(&mut buf).context("recv UDP")?;

            if len < 8 {
                println!("short datagram");
                continue;
            }

            // Decode 64-bit timestamp
            // w0, w1, w2, w3 are int16 (little-endian) -> 8 bytes in total
            let ts = {
                let w0 = LittleEndian::read_u16(&buf[0..2]) as u64;
                let w1 = LittleEndian::read_u16(&buf[2..4]) as u64;
                let w2 = LittleEndian::read_u16(&buf[4..6]) as u64;
                let w3 = LittleEndian::read_u16(&buf[6..8]) as u64;
                w0 | (w1 << 16) | (w2 << 32) | (w3 << 48)
            };

            // println!("IQ: {ts} [{}]", len);

            // Send the info to the matcher
            let pkt = IqPkt {
                tsf: ts,
                bytes: buf[..len].to_vec(),
            };

            match tx.send(pkt).await {
                Ok(_) => {},
                Err(e) => {
                    println!("IQ channel closed ({} packets lost).  Error: {:?}", 
                            tx.len(), e);
                }
            }
        }
    }
}