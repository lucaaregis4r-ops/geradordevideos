"""Perceptual hashing utilities using pure PIL and NumPy.

Provides difference hash (dHash) and discrete cosine transform perceptual hash (pHash),
along with Hamming distance computation and perceptual match verification.
Zero external C dependencies (no imagehash or opencv required).
"""

from __future__ import annotations
import numpy as np
from PIL import Image


def compute_dhash(img: Image.Image, hash_size: int = 8) -> str:
    """Computes difference hash (dHash) of an image.

    Resizes to (hash_size + 1, hash_size) grayscale, compares adjacent horizontal
    pixels, and returns a hex string representing the hash_size^2 bit vector.
    """
    resized = img.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.BILINEAR)
    pixels = np.array(resized, dtype=np.int32)
    diff = pixels[:, :-1] > pixels[:, 1:]
    bit_string = "".join(["1" if b else "0" for b in diff.flatten()])
    return f"{int(bit_string, 2):0{hash_size * hash_size // 4}x}"


def compute_phash(img: Image.Image, hash_size: int = 8, highfreq_factor: int = 4) -> str:
    """Computes DCT-based perceptual hash (pHash) of an image.

    Resizes to (hash_size * highfreq_factor, hash_size * highfreq_factor) grayscale,
    computes 2D Discrete Cosine Transform (DCT-II), extracts the low-frequency
    submatrix, and computes 64 bits compared against the median.
    """
    img_size = hash_size * highfreq_factor  # default 32x32
    resized = img.convert("L").resize((img_size, img_size), Image.Resampling.BILINEAR)
    pixels = np.array(resized, dtype=np.float32)

    # 1D Orthonormal DCT-II Matrix
    N = img_size
    T = np.zeros((N, N), dtype=np.float32)
    for i in range(N):
        alpha = np.sqrt(1.0 / N) if i == 0 else np.sqrt(2.0 / N)
        for j in range(N):
            T[i, j] = alpha * np.cos((np.pi * (2 * j + 1) * i) / (2 * N))

    # 2D DCT: T * pixels * T'
    dct = np.dot(np.dot(T, pixels), T.T)

    # Extract top-left low frequencies (excluding DC at [0, 0] for median calculation)
    low_freq = dct[:hash_size, :hash_size]
    flat_ac = low_freq.flatten()[1:]  # exclude DC term
    med = float(np.median(flat_ac))

    diff = low_freq > med
    bit_string = "".join(["1" if b else "0" for b in diff.flatten()])
    return f"{int(bit_string, 2):0{hash_size * hash_size // 4}x}"


def hamming_distance(hash1: str, hash2: str) -> int:
    """Computes the Hamming distance (differing bit count) between two hex hashes."""
    if not hash1 or not hash2:
        return 64
    try:
        val1 = int(hash1, 16)
        val2 = int(hash2, 16)
        return bin(val1 ^ val2).count("1")
    except ValueError:
        return 64


def is_perceptual_match(hash1: str, hash2: str, max_distance: int = 8) -> bool:
    """Returns True if the Hamming distance between hash1 and hash2 is <= max_distance."""
    if not hash1 or not hash2:
        return False
    return hamming_distance(hash1, hash2) <= max_distance
