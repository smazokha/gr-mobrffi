
#!/bin/bash

docker build -t local/openwifi-armv7 -f docker/armv7.Dockerfile docker/

cross build --release --target armv7-unknown-linux-gnueabihf