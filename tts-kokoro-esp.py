import os
import re
import numpy as np
from onnxruntime import InferenceSession
# --- Use neutral-Spanish IPA G2P ---
from g2p_lib import g2p

# --- Add imports for audio playback ---
try:
    import sounddevice as sd
    import soundfile as sf
    from scipy.io.wavfile import write
    AUDIO_LIBS_AVAILABLE = True
except ImportError:
    AUDIO_LIBS_AVAILABLE = False


def get_phoneme_map():
    """
    Returns the hardcoded phoneme-to-ID mapping.
    """
    phoneme_map = {
        ";": 1, ":": 2, ",": 3, ".": 4, "!": 5, "?": 6, "—": 9, "…": 10,
        "\"": 11, "(": 12, ")": 13, "“": 14, "”": 15, " ": 16, "\u0303": 17,
        "ʣ": 18, "ʥ": 19, "ʦ": 20, "ʨ": 21, "ᵝ": 22, "\uAB67": 23, "A": 24,
        "I": 25, "O": 31, "Q": 33, "S": 35, "T": 36, "W": 39, "Y": 41,
        "ᵊ": 42, "a": 43, "b": 44, "c": 45, "d": 46, "e": 47, "f": 48,
        "h": 50, "i": 51, "j": 52, "k": 53, "l": 54, "m": 55, "n": 56,
        "o": 57, "p": 58, "q": 59, "r": 60, "s": 61, "t": 62, "u": 63,
        "v": 64, "w": 65, "x": 66, "y": 67, "z": 68, "ɑ": 69, "ɐ": 70,
        "ɒ": 71, "æ": 72, "β": 75, "ɔ": 76, "ɕ": 77, "ç": 78, "ɖ": 80,
        "ð": 81, "ʤ": 82, "ə": 83, "ɚ": 85, "ɛ": 86, "ɜ": 87, "ɟ": 90,
        "g": 92, "ɥ": 99, "ɨ": 101, "ɪ": 102, "ʝ": 103, "ɯ": 110, "ɰ": 111,
        "ŋ": 112, "ɳ": 113, "ɲ": 114, "ɴ": 115, "ø": 116, "ɸ": 118, "θ": 119,
        "œ": 120, "ɹ": 123, "ɾ": 125, "ɻ": 126, "ʁ": 128, "ɽ": 129, "ʂ": 130,
        "ʃ": 131, "ʈ": 132, "ʧ": 133, "ʊ": 135, "ʋ": 136, "ʌ": 138, "ɣ": 139,
        "ɤ": 140, "χ": 142, "ʎ": 143, "ʒ": 147, "ʔ": 148, "ˈ": 156, "ˌ": 157,
        "ː": 158, "ʰ": 162, "ʲ": 164, "↓": 169, "→": 171, "↗": 172, "↘": 173,
        "ᵻ": 177
    }
    return phoneme_map


def tokenize_ipa(ipa_text: str, phoneme_to_id: dict, keep_stress_if_mapped: bool = True):
    """
    Greedy longest-match tokenizer aligned to the phoneme vocabulary.
    """
    # --- Gently remove only the outer slashes and surrounding whitespace ---
    s = ipa_text.strip().strip('/')

    # Keep/dismiss primary stress based on whether it's in the map
    if not (keep_stress_if_mapped and 'ˈ' in phoneme_to_id):
        s = s.replace('ˈ', '')

    # Normalization for 'tʃ' ligature if needed
    if 'ʧ' in phoneme_to_id and 'tʃ' not in phoneme_to_id:
        s = s.replace('tʃ', 'ʧ')

    # Greedy longest-match over keys
    keys = sorted(phoneme_to_id.keys(), key=len, reverse=True)
    tokens, unknown = [], []
    i, n = 0, len(s)
    while i < n:
        matched = False
        # Find the longest key in the phoneme map that matches the start of the remaining string
        for k in keys:
            if k and s.startswith(k, i):
                tokens.append(k)
                i += len(k)
                matched = True
                break
        # If no key from the map matches, we have an unknown character
        if not matched:
            unknown.append(s[i])
            i += 1
    return tokens, unknown


def main():
    # --- 1. Load all resources ONCE at the beginning ---
    print("Loading resources, please wait...")

    phoneme_to_id = get_phoneme_map()
    if not phoneme_to_id:
        print("Error: Phoneme map is empty.")
        return

    voice_file = './voices/em_santa.bin'
    try:
        voices = np.fromfile(voice_file, dtype=np.float32).reshape(-1, 1, 256)
    except FileNotFoundError:
        print(f"Error: Voice file '{voice_file}' not found.")
        print("Please make sure the 'voices' directory is in the same location as the script.")
        return
    except Exception as e:
        print(f"Error loading voices from '{voice_file}': {e}")
        return

    model_name = 'model.onnx'
    onnx_path = os.path.join('onnx', model_name)
    try:
        sess = InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
    except Exception as e:
        print(f"Error loading ONNX model from '{onnx_path}': {e}")
        print(f"Please ensure '{model_name}' is in an 'onnx' subdirectory.")
        return

    if not AUDIO_LIBS_AVAILABLE:
        print("\nWarning: `sounddevice`, `soundfile`, or `scipy` not found.")
        print("Audio will be saved but not played automatically.")
        print("Install them with: pip install sounddevice soundfile scipy")

    print("\nResources loaded. Ready for input.")
    print("Enter Spanish text to convert to speech. Press Ctrl+C to exit.")

    # --- 2. Start the main interaction loop ---
    try:
        while True:
            spanish_text = input("\n> ").strip()
            if not spanish_text:
                continue

            ipa = g2p(spanish_text)
            print(f"IPA: {ipa}")

            toks, unknown = tokenize_ipa(ipa, phoneme_to_id, keep_stress_if_mapped=True)
            if unknown:
                print(f"Note: skipped {len(unknown)} unknown character(s) not in your map: {sorted(set(unknown))}")

            try:
                token_ids = [phoneme_to_id[t] for t in toks]
            except KeyError as e:
                print(f"Error: token {e} not found in phoneme map. Aborting this utterance.")
                continue

            print(f"Converted tokens ({len(token_ids)}): {toks}")
            print(f"Token IDs ({len(token_ids)}): {token_ids[:48]}{' …' if len(token_ids) > 48 else ''}")

            if len(token_ids) > 510:
                print("Warning: Text is too long, truncating to 510 tokens.")
                token_ids = token_ids[:510]

            style_index = min(len(token_ids), voices.shape[0] - 1)
            ref_s = voices[style_index]

            input_tokens = np.array([[0, *token_ids, 0]], dtype=np.int64)

            print("Generating audio...")
            audio = sess.run(None, dict(
                input_ids=input_tokens,
                style=ref_s.astype(np.float32, copy=False),
                speed=np.ones(1, dtype=np.float32),
            ))[0]

            output_filename = "output.wav"
            sample_rate = 24000
            wav = np.asarray(audio).squeeze().astype(np.float32)
            write(output_filename, sample_rate, wav)
            print(f"Audio saved to {output_filename}")

            if AUDIO_LIBS_AVAILABLE:
                try:
                    print("Playing audio...")
                    data, fs = sf.read(output_filename, dtype='float32')
                    sd.play(data, fs)
                    sd.wait()
                    print("Playback finished.")
                except Exception as e:
                    print(f"Error playing audio: {e}")

    except KeyboardInterrupt:
        print("\n\nExiting program. Goodbye!")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")


if __name__ == "__main__":
    main()