import sys

try:
    import torch
    print("\n" + "="*50)
    print(" PyTorch CUDA Verification ")
    print("="*50)
    print(f"PyTorch Version: {torch.__version__}")
    
    if torch.cuda.is_available():
        print("✅ CUDA is AVAILABLE!")
        print(f"✅ Device Name: {torch.cuda.get_device_name(0)}")
        print(f"✅ CUDA Version: {torch.version.cuda}")
        print("="*50)
        sys.exit(0)
    else:
        print("❌ CUDA is NOT available.")
        print("PyTorch is using CPU only. This will be very slow for GPT-SoVITS.")
        print("="*50)
        sys.exit(1)
        
except ImportError:
    print("❌ PyTorch is not installed properly.")
    sys.exit(1)
