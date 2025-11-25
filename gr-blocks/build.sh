#!/bin/bash

sudo rm -rf build
mkdir build && cd build
export CMAKE_PREFIX_PATH="$CONDA_PREFIX"
cmake -D CMAKE_INSTALL_PREFIX="$CONDA_PREFIX" ..
sudo make -j"$(nproc)"
sudo make install
sudo ldconfig