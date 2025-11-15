import argparse
import sys
from pathlib import Path
import re
import mido
from music21 import stream, harmony, note, meter, key, instrument, converter

# ==============================================================================
# Builder Logic
# ==============================================================================

def _parse_chords_from_midi(midi_path: Path, ticks_per_quarter: int, debug_mode: bool = False) -> list[harmony.ChordSymbol]:
    """
    Parses a MIDI file for chord symbols using the mido library.
    It looks for chords in two common places:
    1. Yamaha XF-style SysEx messages.
    2. Standard text, lyric, or marker meta-messages.
    """
    chords = []

    # --- Method 1: Yamaha XF Meta Event Parsing Data ---
    # Based on XF Specification Document (xfspc.pdf)
    XF_META_HEADER = (0x43, 0x7B)
    XF_CHORD_ID = 0x01
    XF_LYRIC_ID = 0x20
    XF_RUBY_ID = 0x21

    # Chord Name (ID: 01H) Mappings, based on reverse-engineering the debug output.
    # The key is a tuple of two bytes representing the chord.
    xf_chord_map = {
        (0x31, 0x22): "C#m7", (0x26, 0x02): "Fm7", (0x27, 0x13): "F#add9",
        (0x35, 0x0A): "G#7#9", (0x31, 0x08): "C#sus4", (0x35, 0x13): "G#add9",
        (0x23, 0x13): "D#add9", (0x23, 0x00): "D#", (0x27, 0x00): "F#",
        (0x23, 0x13, 0x27): "D#add9/F#", (0x23, 0x00, 0x35): "D#/G#",
        (0x27, 0x0A): "F#7#9", (0x26, 0x00): "Fm", (0x35, 0x13, 0x37): "G#add9/A#",
        (0x31, 0x0A): "C#7#9", (0x27, 0x0A, 0x22): "F#7#9/C#", (0x35, 0x00): "G#",
        (0x35, 0x00, 0x37): "G#/A#", (0x27, 0x08): "F#sus4",
        (0x35, 0x02): "G#m7", (0x36, 0x13): "Aadd9", (0x44, 0x0A): "E7#9",
        (0x37, 0x08): "A#sus4", (0x32, 0x13, 0x31): "Dm7/C#", (0x32, 0x00): "D",
        (0x45, 0x00): "F", (0x36, 0x00): "A", (0x27, 0x02): "F#m7",
        (0x34, 0x00, 0x23): "Fm/D#", (0x34, 0x00): "Fm", (0x31, 0x00): "C#",
        (0x36, 0x13, 0x41): "Aadd9/C#", (0x34, 0x13, 0x23): "Fmadd9/D#",
        # Add new chords found in the latest debug output
        (0x23, 0x13, 0x22): "D#add9/C#", (0x23, 0x00, 0x27): "D#/F#",
        (0x44, 0x13): "Eadd9", (0x32, 0x08): "Dsus4", (0x31, 0x13): "C#add9",
        (0x36, 0x0A): "A7#9", (0x32, 0x0A): "D7#9",
        (0x52, 0, 35): "Fm/D#", (0x52, 19, 35): "Fmadd9/D#"
    }

    try:
        mf = mido.MidiFile(str(midi_path))
        # If the chord file has a different TPQ, it might affect timing.
        # We'll use the one from the melody file, but warn the user.
        if mf.ticks_per_beat != ticks_per_quarter:
            print(f"  - Warning: TPQ mismatch. Melody file has {ticks_per_quarter}, chord file has {mf.ticks_per_beat}. Using melody's TPQ for timing.")
    except Exception as e:
        print(f"❌ Error: Failed to open or parse MIDI file with mido: {midi_path}. Details: {e}", file=sys.stderr)
        return []

    absolute_time_ticks = 0
    # mido.merge_tracks provides a single, time-ordered stream of all messages.
    for msg in mido.merge_tracks(mf.tracks):
        # msg.time is the delta time in ticks from the previous event.
        absolute_time_ticks += msg.time
        current_chord_text = None

        # --- Method 1: Check for Yamaha XF Meta Events ---
        if msg.type == 'sequencer_specific' and len(msg.data) > 2 and msg.data[:2] == XF_META_HEADER:
            data = msg.data
            event_id = data[2]

            if debug_mode:
                data_hex = ' '.join(f'{b:02X}' for b in data)
                print(f"  - DEBUG [TICK {absolute_time_ticks}]: Found XF Meta Event. ID: {event_id:02X}, Len: {len(data)}, Data: {data_hex}")

            if event_id == XF_CHORD_ID:
                # The actual data payload starts after the header and ID
                payload = data[3:]
                # Filter out the 7F terminators/separators
                chord_bytes = tuple(b for b in payload if b != 0x7F)

                if not chord_bytes:
                    continue

                # Look up the byte sequence in our new map
                current_chord_text = xf_chord_map.get(chord_bytes)

                if debug_mode and current_chord_text:
                    print(f"    - Parsed chord bytes {chord_bytes} as '{current_chord_text}'")

        # --- Method 2: Check for standard Text/Lyric/Marker Meta-Events ---
        elif msg.is_meta and msg.type in ['text', 'lyrics', 'marker']:
            # The text attribute is 'name' for 'track_name' and 'text' for others.
            if msg.type == 'track_name':
                text = msg.name
            else:
                text = msg.text
            text = text.strip()

            if debug_mode and text:
                print(f"  - DEBUG [TICK {absolute_time_ticks}]: Found text in '{msg.type}': '{text}'")

            if text:
                # Expanded regex to find chord-like strings.
                # This is more permissive and handles variations like "C_maj", "Gm7", "C(add9)" etc.
                # It also strips surrounding characters like brackets or spaces.
                # The core of the chord is captured in group 1.
                match = re.search(r'[^A-G]*([A-G][b#]?(?:maj|min|m|M|dim|aug|sus|add|[-_])?[0-9]*(?:\(.*\))?(?:/[A-G][b#]?)?)\b', text)

                if match:
                    parsed_text = match.group(1)
                    try:
                        # Validate that music21 can understand this chord text
                        harmony.ChordSymbol(parsed_text)
                        current_chord_text = parsed_text
                    except Exception:
                        if debug_mode:
                            print(f"  - DEBUG: Text '{parsed_text}' looked like a chord but failed to parse.")
                        pass # Not a valid chord symbol, ignore.

        # --- If a chord was found, create the music21 ChordSymbol object ---
        if current_chord_text:
            try:
                cs = harmony.ChordSymbol(current_chord_text)
                # Set the position in quarter notes
                cs.offset = absolute_time_ticks / ticks_per_quarter
                chords.append(cs)
            except Exception as e:
                print(f"Warning: Could not create chord from text '{current_chord_text}'. Details: {e}", file=sys.stderr)

    print(f"  - Scanned MIDI data and found {len(chords)} chord symbols.")
    return chords

def create_lead_sheet(chord_midi_path: Path, melody_midi_path: Path, output_xml_path: Path):
    """
    Generates a MusicXML lead sheet by merging chords and melody from two MIDI files.
    """
    # 1. Parse melody file to get timing info (ticks per quarter note) and musical data
    print("  - Parsing melody file...")
    try:
        melody_mf = mido.MidiFile(str(melody_midi_path))
        ticks_per_quarter = melody_mf.ticks_per_beat
        # Use music21's converter for high-level musical structure
        melody_score = converter.parse(str(melody_midi_path))
    except Exception as e:
        print(f"❌ Error: Could not parse melody file {melody_midi_path}. Details: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Find the melody part (assuming it's on MIDI channel 1)
    parts = instrument.partitionByInstrument(melody_score)
    melody_part = next((p for p in parts if p.getInstrument() and p.getInstrument().midiChannel == 1), None)
    if not melody_part:
        print("❌ Error: Could not find a melody part on MIDI channel 1 in the melody file.", file=sys.stderr)
        sys.exit(1)
    melody_part.id = 'melody'

    # 3. Extract chords from the chord file using the timing from the melody file
    print("  - Parsing chord file for chord symbols...")
    extracted_chords = _parse_chords_from_midi(chord_midi_path, ticks_per_quarter)
    if not extracted_chords:
        print("Warning: No chord symbols were found in the chord file.")

    # 4. Get metadata (Time Signature, Key Signature) from the melody
    ts = melody_part.getElementsByClass(meter.TimeSignature).first()
    ks = melody_part.getElementsByClass(key.KeySignature).first()

    # 5. Create the new lead sheet structure
    lead_sheet = stream.Score()
    output_part = stream.Part()
    output_part.id = 'lead_sheet_part'

    # Insert metadata
    if ts: output_part.insert(0, ts)
    if ks: output_part.insert(0, ks)

    # 6. Insert chords and melody notes into the output part
    print(f"  - Merging {len(extracted_chords)} chords and melody...")
    for cs in extracted_chords:
        output_part.insert(cs.offset, cs)
    for el in melody_part.notesAndRests:
        output_part.insert(el.offset, el)

    # 7. Add the completed part to the score and write to file
    lead_sheet.insert(0, output_part)
    print(f"  - Writing to MusicXML file: {output_xml_path}")
    output_xml_path.parent.mkdir(parents=True, exist_ok=True)
    lead_sheet.write('musicxml', fp=str(output_xml_path))

# ==============================================================================
# Command-line execution logic
# ==============================================================================

def check_chords_in_file(file_path: Path):
    """Checks a single MIDI file for chord information and prints debug output."""
    print(f"Checking for chords in: {file_path}")
    if not file_path.exists():
        print(f"❌ Error: File not found at {file_path}", file=sys.stderr)
        sys.exit(1)
    try:
        # For checking, we just need the TPQ from the file itself.
        mf = mido.MidiFile(str(file_path))
        chords = _parse_chords_from_midi(file_path, mf.ticks_per_beat, debug_mode=True)
        if chords:
            print(f"\n✅ Found {len(chords)} chords in the file.")
        else:
            print("\nℹ️ No chord symbols were found in the file.")
    except Exception as e:
        print(f"\n❌ An error occurred while checking the file: {e}", file=sys.stderr)
        sys.exit(1)

def run_lead_sheet_generation(chord_file: Path, melody_file: Path, output_file: Path):
    """Runs the full lead sheet generation process."""
    print("Starting lead sheet generation...")
    print(f"  - Chord source:  {chord_file}")
    print(f"  - Melody source: {melody_file}")
    print(f"  - Output file:   {output_file}")
    create_lead_sheet(chord_file, melody_file, output_file)
    print(f"\n✅ Successfully created lead sheet: {output_file.resolve()}")

def main():
    """
    Main function to parse command-line arguments and run the script.
    """
    parser = argparse.ArgumentParser(
        description="Tools for building a MusicXML lead sheet from MIDI files.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""\
Examples:
  # Generate a lead sheet
  python main.py --chord-file input/chords.mid --melody-file input/melody.mid --output output/sheet.xml

  # Check a single MIDI file for chord information
  python main.py --check-chords "yoasobi_yorunikakeru.mid"
"""
    )
    # Group for lead sheet generation
    gen_group = parser.add_argument_group('Lead Sheet Generation')
    gen_group.add_argument("--chord-file", type=Path, help="Path to the MIDI file containing chord data (SysEx or text).")
    gen_group.add_argument("--melody-file", type=Path, help="Path to the MIDI file containing the cleaned-up melody.")
    gen_group.add_argument("--output", type=Path, help="Path for the generated MusicXML file.")

    # Group for utility functions
    util_group = parser.add_argument_group('Utilities')
    util_group.add_argument("--check-chords", type=Path, help="Check a single MIDI file for chord information and exit.")

    args = parser.parse_args()

    # --- Handle Chord Check Utility ---
    if args.check_chords:
        check_chords_in_file(args.check_chords)
        sys.exit(0)

    # --- Handle Lead Sheet Generation ---
    elif args.chord_file and args.melody_file and args.output:
        try:
            run_lead_sheet_generation(
                chord_file=args.chord_file,
                melody_file=args.melody_file,
                output_file=args.output
            )
        except Exception as e:
            print(f"\n❌ An unexpected error occurred: {e}", file=sys.stderr)
            sys.exit(1)
        sys.exit(0)
    else:
        # If no action is specified, print help.
        if not any(vars(args).values()):
             parser.print_help()
        else:
             print("For lead sheet generation, you must provide --chord-file, --melody-file, and --output.", file=sys.stderr)
             print("Use --help for more options.", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
