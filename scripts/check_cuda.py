"""Fail clearly if the configured Laya device cannot use CUDA."""
import sys

try:
    import torch
except ImportError:
    sys.exit("PyTorch is not installed. Install a CUDA-enabled PyTorch build, then install requirements.txt.")

if not torch.cuda.is_available():
    sys.exit("CUDA is not available in this PyTorch environment. LayaDesk will not fall back to CPU.")

device = torch.cuda.get_device_properties(0)
free, total = torch.cuda.mem_get_info(0)
print(f"CUDA ready: {device.name}, compute capability {device.major}.{device.minor}, free VRAM {free / 2**30:.2f}/{total / 2**30:.2f} GiB")
