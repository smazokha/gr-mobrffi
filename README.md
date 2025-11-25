# Real-time Device Fingerprinting and Re-identification in GNUradio
Presented at the GRCon25 on Sep 10, 2025 [GRCon25 Page](https://events.gnuradio.org/event/26/contributions/773/)<br/>
Presentation Recording: [YouTube](https://youtu.be/Csf4K1x2vRU?t=13198)<br/>
Gr-MobRFFI Paper: [Link](https://events.gnuradio.org/event/26/contributions/773/attachments/229/665/gr-mobrffi_paper_v1.2.pdf)<br/>
Quick Tool Demo: [Loom Video](https://www.loom.com/share/01ebceca39c5486fb71886151e653acb)

## Brief Intro

This repository contains the source code that was developed as part of the `gr-mobrffi` project -- a method for evaluating WiFi device fingerprinting models in GNUradio.

The project consists of the following components:

* `alfa-tx`: Bash script that is used to initiate injection of WiFi probe requests from the Alfa sniffer devices, connected to a remote Raspberry Pi device (please see below);

    **Note**: this project relies on another project, developed by my PhD co-conspirator, Dr. Fanchen Bao [probe_request_injection](https://github.com/FanchenBao/probe_request_injection). You will have to download it into your home directory, and install all the required libraries (follow the repo instructions).

* `antsdr-decoder`: Rust-based app that runs on AntSDR, captures RadioTap headers, matches them with IQ samples from the DMA buffer, and finally sends to the host for further processing in GNUradio.

    **Note**: this app must be compiled and installed on [OpenWiFi-based AntSDR firmware](https://github.com/open-sdr/openwifi).

* `host-receiver`: Python-based app that can be used to (a) capture & store the IQ samples for RFFI model training, (b) evaluate whether the AntSDR can see the relevant WiFi traffic, 

* `gr-blocks`: A suite of GNUradio blocks that can be used for real-time WiFi device fingerprinting. 

    **Note**: These blocks have to be compiled, and installed in GNUradio. To run these blocks, you need to have a pre-trained RFFI model, your Python env needs to have ChromaDB installed (locally-hosted vector DB), and a threshold that can be used for deciding whether the devices are new or known (please see our [paper](https://arxiv.org/abs/2503.02156) about this).

## Hardware & Software Requirements

To run `gr-mobrffi`, you have the following requirements:

* Your Wifi emitters (for our experiment, we used [Alfa AWUS036ACH](https://www.amazon.com/ALFA-AWUS036ACH-%E3%80%90Type-C%E3%80%91-Long-Range-Dual-Band/dp/B08SJC78FH))

* [AntSDR E200](https://www.crowdsupply.com/microphase-technology/antsdr-e200) for capturing & decoding WiFi frames;

    **Note**: AntSDR must be running [OpenWiFi firmware](https://github.com/open-sdr/openwifi) with a custom-compiled version of the ow-capture firmware (which is sending data to local IP address instead of to the host);

* Linux host running Ubuntu 20.04 with GNUradio 3.10 installed via Miniconda environment, ideally with CUDA (though, you can run inference on CPU too).

## Instructions

1. Connect & configure the WiFi transmitters. 

    If you are using Alfa sniffers, ensure that they are all connected to your USB hub, and configured in monitor mode on 36th channel @ 5 GHz WiFi. The AntSDR decoder is configured to capture **only** WiFi probe requests with a fixed MAC address `11:22:33:44:55:66` (only for filtering devices for the experiment, not for fingerprinting). 

    In case you're using the ~[tx.sh script](./alfa-tx/tx.sh), please note that all the Alfa sniffers were connected simultaneously to a Raspberry Pi with pre-configured interface aliases (e.g., alfa_01, alfa_02, etc). To initiate or stop probe request injection, the host connects, and launches a `tmux` session on Raspberry Pi via SSH. 

2. Prepare the `conda` environment:

    * First, create a conda environment with all the necessary packages: `conda env create -f ./gr-blocks/grmobrffi.yml --name grmobrffi`

    * Activate the environment: `conda activate grmobrffi`

    * Then, install the GNUradio blocks: `sudo chmod +x ./gr-blocks/build.sh && ./build.sh`

2. Launch the GNUradio via `gnuradio-companion` command, open the flowchart ![example.grc](./gr-blocks/examples/example.grc), and configure the parameters:

    * `threshold`: this is the value that is used to determine fingerprint distance (values above let us assume that the device is unknown, and values below are known / enrolled);

    * Rational Resampler ratios: in our case, we're sampling at 20 Msps, which produces 320 IQ samples per preamble; but the model we used for testing was trained using data on 25 Msps rate (400 IQ samples). Therefore, the resampler allows us to upsample the signal. Adjust according to your signal capture settings.

    * Input Vector Length, Output Embedding Length: Adjust these based on input and output dimensions of your fingerprinting model.

    * Chroma persist directory: this is the path where the script will store the Chroma database file containing device embedding vectors.

    * ONNX model path: this is the path to the RFFI model, stored in ONNX format. You can consider exploring [our previous project](https://github.com/I-SENSE/mobintel-rffi-paper) and adopt our model training code for your project.

3. Launch the `antsdr-decoder` app:

    * Ensure that your AntSDR is running [OpenWiFi firmware](https://github.com/open-sdr/openwifi);

    * Replace the standard binary TODO

    * Transfer the config [bash script](./antsdr-decoder/sensor_configure.sh) into AntSDR home directory to configure the device (or run commands manually);

    * Compile and deploy the `ow-capture` app to AntSDR using [deploy.sh script](./antsdr-decoder/deploy.sh)

        **Note**: This script hasn't been thoroughly tested ourside of my dev environment. Please, review the code and ensure that each step is correctly executed on your machine. The main goal of the script is to compile the Rust app, and transfer the binary `ow-capture` to AntSDR.

    * Run the `ow-capture` binary (it should start streaming IQ and radiotap data to the host).

## Capturing Your Own Dataset

This project also includes a helpful script which should allow you to evaluate your signal capture and, as an example, capture your own IQ dataset from AntSDR. This might become quite handy as you train your own RFFI model, using your own fleet of devices.

To do this, explore the [host-receiver app](./host-receiver/app.py). The app can operate in several modes:

* **Individual mode**: the app is receiving decoded frames from the AntSDR and displays frame capture rate in real time;
* **Combined mode**: the app is still capturing decoded frames, but from two AntSDR devices simultaneously (with a goal of verifying how many frames can be captured by both devices simultaneously);
* **Capture mode**: this mode is dedicated to simply capturing frames and storing them for further processing (e.g., model training).






