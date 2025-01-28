import re
import json
from typing import Dict, List
from termcolor import colored

# def print_header(text, level=0, decorator='=', decorator_len=5):
#     """Print a header with a given decorator and text."""
#     indent = " " * (level * 2)
#     print(f"{indent}{decorator * decorator_len} {text} {decorator * decorator_len}")

def print_header(text: str, level: int = 0, decorator: str = '', decorator_len: int = 5, color: str = 'cyan', attrs: List[str] = None):
    """Print a formatted header with indentation and color."""
    indent = "  " * level
    print(colored(
        f"{indent}{decorator * decorator_len} {text} {decorator * decorator_len}",
        color,
        attrs=attrs
    ))
    
def chunk_text(text: str, max_chunk_size: int = 1000, max_overlap: int = 200) -> List[str]:
    """
    Chunks text into segments of max_chunk_size, preserving full sentences and ensuring
    overlap between chunks doesn't exceed max_overlap. Retains newlines and doesn't split words.

    Args:
        text (str): Input text
        max_chunk_size (int): Maximum chunk size
        max_overlap (int): Maximum overlap between chunks

    Returns:
        list: List of text chunks
    """

    # Split text into sentences
    def _split_into_sentences(text): return re.split(r'(?<=[.!?])\s+', text)
    sentences = _split_into_sentences(text)

    # Iterate over each sentence to create chunks
    chunks, current_chunk, overlap = [], "", ""
    for sentence in sentences:
        # Add sentence to the current chunk if it doesn't exceed max_chunk_size
        if len(current_chunk) + len(sentence) <= max_chunk_size:
            current_chunk += sentence + " "
        else:
            # Else add the current chunk to the list and start a new one
            chunks.append(current_chunk.strip())

            # Create overlap by taking the last sentences from the current chunk that fit within max_overlap
            overlap = ""
            chunk_sentences = _split_into_sentences(current_chunk)
            for s in reversed(chunk_sentences):
                if len(overlap) + len(s) > max_overlap:
                    break
                overlap = s + " " + overlap
            
            # Start new chunk with overlap and the new sentence
            current_chunk = overlap + sentence + " "

    # Add the last chunk if it's not empty
    if current_chunk.strip(): chunks.append(current_chunk.strip())

    return chunks