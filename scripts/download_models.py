import os
import urllib.request
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Official GPT-SoVITS pre-trained models from HuggingFace
MODELS = {
    "GPT_SoVITS/pretrained_models/s1bert25hz-2kh-longer-epoch-0-step-0.ckpt": "https://huggingface.co/lj1995/GPT-SoVITS/resolve/main/s1bert25hz-2kh-longer-epoch-0-step-0.ckpt",
    "GPT_SoVITS/pretrained_models/s2G488k.pth": "https://huggingface.co/lj1995/GPT-SoVITS/resolve/main/s2G488k.pth",
    "GPT_SoVITS/pretrained_models/s2D488k.pth": "https://huggingface.co/lj1995/GPT-SoVITS/resolve/main/s2D488k.pth",
    "GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large/pytorch_model.bin": "https://huggingface.co/hfl/chinese-roberta-wwm-ext-large/resolve/main/pytorch_model.bin",
    "GPT_SoVITS/pretrained_models/chinese-hubert-base/pytorch_model.bin": "https://huggingface.co/TencentGameMate/chinese-hubert-base/resolve/main/pytorch_model.bin"
}

def download_file(url: str, dest_path: str):
    if os.path.exists(dest_path):
        logger.info(f"✅ Already exists: {dest_path}")
        return
        
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    logger.info(f"⬇️ Downloading {url} ...")
    
    try:
        urllib.request.urlretrieve(url, dest_path)
        logger.info(f"✅ Successfully downloaded to {dest_path}")
    except Exception as e:
        logger.error(f"❌ Failed to download {url}. Error: {e}")

def main():
    print("\n" + "="*50)
    print(" Downloading GPT-SoVITS Pre-trained Base Models ")
    print("="*50)
    
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend", "voice", "gpt_sovits_core"))
    
    for relative_path, url in MODELS.items():
        full_path = os.path.join(base_dir, relative_path)
        download_file(url, full_path)
        
    print("\n" + "="*50)
    print(" 🎉 All models downloaded successfully! ")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()
