#!/usr/bin/env python3
"""Profile OCR pipeline to identify bottlenecks and optimization opportunities."""
import time
import hashlib
from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageDraw, ImageFont

def create_test_image(width=1920, height=1080, text="Test"):
    """Create a test image for OCR profiling."""
    img = Image.new("RGB", (width, height), color=(240, 240, 240))
    draw = ImageDraw.Draw(img)

    # Try to use a default font, otherwise use basic text
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
    except:
        font = ImageFont.load_default()

    # Draw some text
    draw.text((100, 100), text, fill=(0, 0, 0), font=font)
    draw.text((100, 200), "More test text here", fill=(0, 0, 0), font=font)
    draw.text((100, 300), "Additional line", fill=(0, 0, 0), font=font)

    return img

# Constants from OCR module
PREPROCESS_DEFAULT = True
_MAX_OCR_RESOLUTION = (1920, 1080)
_PREPROCESS_DEFAULT = True

def _image_cache_key(img: Image.Image, preprocess: bool = PREPROCESS_DEFAULT) -> str:
    """Generate cache key for image."""
    h = hashlib.sha256()
    h.update(img.tobytes())
    if preprocess:
        h.update(b":preprocessed")
    return h.hexdigest()

def _downsample_if_needed(img: Image.Image) -> Image.Image:
    """Downsample image if it exceeds maximum OCR resolution."""
    if img.width > _MAX_OCR_RESOLUTION[0] or img.height > _MAX_OCR_RESOLUTION[1]:
        img.thumbnail(_MAX_OCR_RESOLUTION, Image.Resampling.LANCZOS)
    return img

def preprocess_for_ocr(img: Image.Image) -> Image.Image:
    """Apply preprocessing to improve OCR accuracy."""
    # Convert to grayscale
    if img.mode != "L":
        img = img.convert("L")

    # Increase contrast
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.0)

    # Apply binarization threshold
    img = img.point(lambda x: 0 if x < 128 else 255, "1")

    # Resize to 2x
    img = img.resize((img.width * 2, img.height * 2), Image.Resampling.LANCZOS)

    return img

def profile_ocr_functions():
    """Profile various OCR operations to measure performance."""
    results = {}

    print("Creating test images...")
    test_img = create_test_image()
    large_img = create_test_image(width=2560, height=1440)  # 2K resolution
    xk_img = create_test_image(width=3840, height=2160)  # 4K resolution

    # Profile preprocessing
    print("\n1. Profiling preprocessing...")
    start = time.time()
    preprocessed = preprocess_for_ocr(test_img)
    preprocess_time = time.time() - start
    results['preprocess_1080p'] = preprocess_time
    print(f"   1080p preprocessing: {preprocess_time:.3f}s")

    start = time.time()
    preprocessed_large = preprocess_for_ocr(large_img)
    preprocess_large_time = time.time() - start
    results['preprocess_1440p'] = preprocess_large_time
    print(f"   1440p preprocessing: {preprocess_large_time:.3f}s")

    start = time.time()
    preprocessed_xk = preprocess_for_ocr(xk_img)
    preprocess_xk_time = time.time() - start
    results['preprocess_2160p'] = preprocess_xk_time
    print(f"   2160p (4K) preprocessing: {preprocess_xk_time:.3f}s")

    # Profile downsample
    print("\n2. Profiling downsampling...")
    start = time.time()
    downsampled = _downsample_if_needed(large_img)
    downsample_time = time.time() - start
    results['downsample_2K_to_1080p'] = downsample_time
    print(f"   2K → 1080p downsampling: {downsample_time:.3f}s")

    start = time.time()
    downsampled_xk = _downsample_if_needed(xk_img)
    downsample_xk_time = time.time() - start
    results['downsample_4K_to_1080p'] = downsample_xk_time
    print(f"   4K → 1080p downsampling: {downsample_xk_time:.3f}s")

    # Profile cache operations
    print("\n3. Profiling cache operations...")
    start = time.time()
    key = _image_cache_key(test_img, preprocess=True)
    cache_key_time = time.time() - start
    results['cache_key_generation'] = cache_key_time
    print(f"   Cache key generation: {cache_key_time:.6f}s")

    # Profile combined operations
    print("\n4. Profiling combined operations...")
    start = time.time()
    downsampled = _downsample_if_needed(xk_img)
    preprocessed = preprocess_for_ocr(downsampled)
    combined_time = time.time() - start
    results['downsample_preprocess_4K'] = combined_time
    print(f"   4K downsample + preprocess: {combined_time:.3f}s")

    start = time.time()
    preprocessed = preprocess_for_ocr(test_img)
    direct_time = time.time() - start
    results['direct_preprocess_1080p'] = direct_time
    print(f"   1080p direct preprocess: {direct_time:.3f}s")

    return results

def identify_bottlenecks(results):
    """Identify potential bottlenecks based on profiling results."""
    print("\n=== BOTTLENECK ANALYSIS ===\n")

    # Identify operations that take more than 100ms
    bottlenecks = [k for k, v in results.items() if v > 0.1]

    if bottlenecks:
        print("Potential bottlenecks (>100ms):")
        for op in bottlenecks:
            print(f"  - {op}: {results[op]:.3f}s")
    else:
        print("No significant bottlenecks found (>100ms)")

    # Compare high-resolution operations
    if 'preprocess_1080p' in results and 'preprocess_1440p' in results:
        ratio = results['preprocess_1440p'] / results['preprocess_1080p']
        print(f"\n1440p vs 1080p preprocessing ratio: {ratio:.2f}x")

    if 'preprocess_1080p' in results and 'preprocess_2160p' in results:
        ratio = results['preprocess_2160p'] / results['preprocess_1080p']
        print(f"4K vs 1080p preprocessing ratio: {ratio:.2f}x")
        if ratio > 2.0:
            print("  → High-resolution images significantly slower, implement downsampling")

    # Check downsample effectiveness
    if 'downsample_preprocess_4K' in results and 'preprocess_2160p' in results:
        speedup = results['preprocess_2160p'] / results['downsample_preprocess_4K']
        print(f"\nDownsampling speedup (4K): {speedup:.2f}x")
        if speedup > 1.5:
            print("  → Downsampling is very effective for high-resolution images")

    # Check cache overhead
    if 'cache_key_generation' in results:
        cache_overhead = results['cache_key_generation'] * 1000  # in ms
        print(f"\nCache key generation overhead: {cache_overhead:.2f}ms")
        if cache_overhead > 5:
            print("  → Cache key generation is expensive, consider simpler hash")

def suggest_optimizations(results):
    """Suggest specific optimizations based on profiling results."""
    print("\n=== OPTIMIZATION SUGGESTIONS ===\n")

    suggestions = []

    # Check if preprocessing is a bottleneck
    if results.get('preprocess_1080p', 0) > 0.1:
        suggestions.append("1. Preprocessing takes >100ms - consider parallel processing or GPU acceleration")

    # Check if high-resolution processing is slow
    if results.get('preprocess_2160p', 0) > 0.3:
        suggestions.append("2. 4K preprocessing is slow (>300ms) - implement aggressive downsampling")

    # Check downsample effectiveness
    downsample_speedup = results.get('preprocess_2160p', 1) / max(results.get('downsample_preprocess_4K', 1), 0.001)
    if downsample_speedup > 2:
        suggestions.append(f"3. Downsampling provides {downsample_speedup:.1f}x speedup - make it default for >1080p")

    # Check if caching is worth it
    cache_overhead = results.get('cache_key_generation', 0) * 1000
    if cache_overhead < 1:
        suggestions.append("4. Cache key generation is fast (<1ms) - caching is highly efficient")

    # General optimizations
    suggestions.append("\n5. Consider implementing:")
    suggestions.append("   - Region-of-interest OCR to avoid full-screen processing")
    suggestions.append("   - Lazy preprocessing (only when needed)")
    suggestions.append("   - Thumbnail-based OCR for initial pass, then detail if needed")
    suggestions.append("   - Async OCR operations for non-blocking text extraction")

    for suggestion in suggestions:
        print(suggestion)

def main():
    """Main profiling function."""
    print("=== OCR PIPELINE PROFILING ===\n")
    print("This script profiles the OCR pipeline to identify bottlenecks...\n")

    results = profile_ocr_functions()
    identify_bottlenecks(results)
    suggest_optimizations(results)

    print(f"\n=== PROFILING COMPLETE ===")
    print(f"Total operations profiled: {len(results)}")
    print(f"Total time measured: {sum(results.values()):.3f}s")

    return results

if __name__ == "__main__":
    main()