#!/bin/bash

cd /root/openwifi

# Configure the device to get access to the radio module
./wgd.sh

# Enable monitor mode on channel 36 (5 GHz)
./monitor_ch.sh sdr0 36

# Install the driver and configure the buffer size of 4095
insmod side_ch.ko iq_len_init=4095

# Determine the offset after the trigger (1000 for testing, 500 for prod)
#./side_ch_ctl wh11d500
./side_ch_ctl wh11d1000

# Configure the frame capture trigger type
#./side_ch_ctl wh8d9
./side_ch_ctl wh8d4

# Set gain to manual (NOT AGC!)
./set_rx_gain_manual.sh 30

echo "Setup completed."