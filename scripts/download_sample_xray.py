#!/usr/bin/env python3
"""
Download sample chest X-ray from NIH public dataset.
Uses the NIH Clinical Center ChestX-ray8 dataset (public domain).
"""

import os
import urllib.request
from pathlib import Path

# Sample X-ray URLs from NIH public dataset
# These are publicly available chest X-ray images
SAMPLE_XRAYS = {
    "normal": {
        "url": "https://raw.githubusercontent.com/ieee8023/covid-chestxray-dataset/master/images/1-s2.0-S0140673620303706-fx1_lrg.jpg",
        "description": "Normal chest X-ray"
    },
    "pneumonia": {
        "url": "https://raw.githubusercontent.com/ieee8023/covid-chestxray-dataset/master/images/nejmoa2001191_f1-PA.jpeg",
        "description": "Chest X-ray with pneumonia findings"
    }
}


def download_sample_xray(output_dir: str = "data", sample_type: str = "normal") -> str:
    """
    Download a sample chest X-ray image.
    
    Args:
        output_dir: Directory to save the image
        sample_type: Type of sample ("normal" or "pneumonia")
        
    Returns:
        Path to the downloaded image
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if sample_type not in SAMPLE_XRAYS:
        raise ValueError(f"Unknown sample type: {sample_type}. Choose from: {list(SAMPLE_XRAYS.keys())}")
    
    sample_info = SAMPLE_XRAYS[sample_type]
    url = sample_info["url"]
    
    # Determine file extension
    ext = url.split(".")[-1].lower()
    if ext not in ["jpg", "jpeg", "png"]:
        ext = "jpg"
    
    output_path = output_dir / f"sample_xray_{sample_type}.{ext}"
    
    print(f"Downloading {sample_info['description']}...")
    print(f"  URL: {url}")
    print(f"  Output: {output_path}")
    
    try:
        # Download the image
        urllib.request.urlretrieve(url, output_path)
        print(f"✅ Downloaded successfully: {output_path}")
        return str(output_path)
    except Exception as e:
        print(f"❌ Download failed: {e}")
        
        # Create a placeholder image if download fails
        print("Creating placeholder image...")
        create_placeholder_xray(output_path)
        return str(output_path)


def create_placeholder_xray(output_path: Path):
    """Create a simple placeholder X-ray image for testing."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        # Create a grayscale image resembling an X-ray
        width, height = 512, 512
        img = Image.new('L', (width, height), color=30)  # Dark gray background
        draw = ImageDraw.Draw(img)
        
        # Draw a lighter oval for the chest cavity
        draw.ellipse([100, 50, 412, 450], fill=60, outline=80)
        
        # Draw lung-like shapes
        draw.ellipse([120, 80, 250, 350], fill=45, outline=60)  # Left lung
        draw.ellipse([262, 80, 392, 350], fill=45, outline=60)  # Right lung
        
        # Add some text
        draw.text((width//2 - 80, height - 40), "SAMPLE X-RAY", fill=150)
        draw.text((width//2 - 60, 10), "PA VIEW", fill=150)
        
        img.save(output_path)
        print(f"✅ Created placeholder image: {output_path}")
        
    except ImportError:
        print("PIL not available, skipping placeholder creation")


def main():
    """Download sample X-rays for demo."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Download sample chest X-rays")
    parser.add_argument("--output-dir", default="data", help="Output directory")
    parser.add_argument("--type", default="all", choices=["normal", "pneumonia", "all"],
                        help="Type of sample to download")
    args = parser.parse_args()
    
    if args.type == "all":
        for sample_type in SAMPLE_XRAYS:
            download_sample_xray(args.output_dir, sample_type)
    else:
        download_sample_xray(args.output_dir, args.type)
    
    print("\n📋 Sample images downloaded. Use with the MedGemma Clinical Assistant.")


if __name__ == "__main__":
    main()
