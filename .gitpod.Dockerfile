FROM gitpod/workspace-full

USER gitpod

# System dependencies for Kivy & OBD
RUN sudo apt-get update && sudo apt-get install -y \
    python3-pip python3-dev \
    libgl1-mesa-dev x11-utils \
    libmtdev-dev libusb-1.0-0-dev \
    build-essential git

# Install Python packages
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt
